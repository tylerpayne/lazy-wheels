"""GitHub API client using httpx with connection reuse and ETag caching."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import httpx

_client: httpx.Client | None = None
_cached_repo: str | None = None


def _get_client() -> httpx.Client | None:
    """Return a shared httpx client with GitHub auth (created once)."""
    global _client
    if _client is not None:
        return _client
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        result = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, check=False
        )
        if result.returncode == 0 and result.stdout.strip():
            token = result.stdout.strip()
    if not token:
        return None
    _client = httpx.Client(
        base_url="https://api.github.com",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
        follow_redirects=True,
    )
    return _client


def _get_repo() -> str | None:
    """Get the current repo as ``owner/name`` from git remote URL."""
    global _cached_repo
    if _cached_repo is not None:
        return _cached_repo
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        url = result.stdout.strip()
        m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
        if m:
            _cached_repo = m.group(1)
            return _cached_repo
    return None


def _cache_dir() -> Path:
    """Return the cache directory, creating it if needed."""
    d = Path.cwd() / ".uvr" / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_cache() -> dict:
    """Load the releases cache file."""
    path = _cache_dir() / "releases.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_cache(data: dict) -> None:
    """Save the releases cache file."""
    path = _cache_dir() / "releases.json"
    path.write_text(json.dumps(data))


def list_release_tag_names() -> set[str]:
    """Fetch all GitHub release tag names for the current repo.

    Uses ETag-based conditional requests — returns cached data on 304.
    Paginates automatically. Returns an empty set on auth or network failure.
    """
    client = _get_client()
    repo = _get_repo()
    if not client or not repo:
        return set()

    cache = _load_cache()
    etag = cache.get("etag", "")
    cached_tags = cache.get("tags", [])

    # First page with conditional request
    headers: dict[str, str] = {}
    if etag:
        headers["If-None-Match"] = etag

    url = f"/repos/{repo}/releases?per_page=100"
    try:
        resp = client.get(url, headers=headers)
        if resp.status_code == 304:
            # Nothing changed — use cached data
            return set(cached_tags)
        resp.raise_for_status()
    except (httpx.HTTPError, KeyError):
        # Network error — fall back to cache if available
        return set(cached_tags) if cached_tags else set()

    # Full fetch (200) — collect all pages
    first_etag = resp.headers.get("etag", "")
    tag_names: set[str] = set()
    for release in resp.json():
        tag_names.add(release["tag_name"])

    next_url = _next_page(resp.headers.get("link"))
    while next_url:
        try:
            resp = client.get(next_url)
            resp.raise_for_status()
            for release in resp.json():
                tag_names.add(release["tag_name"])
            next_url = _next_page(resp.headers.get("link"))
        except (httpx.HTTPError, KeyError):
            break

    # Save cache with ETag from the first page
    _save_cache({"etag": first_etag, "tags": sorted(tag_names)})

    return tag_names


def check_release_exists(tag: str) -> bool:
    """Check if a GitHub release exists for the given tag.

    Uses a targeted API call with ETag caching — returns cached result
    on 304. Only makes a network call if the cache is missing or stale.
    """
    client = _get_client()
    repo = _get_repo()
    if not client or not repo:
        return False

    # Load per-tag cache
    cache = _load_cache()
    tag_cache = cache.get("tags_checked", {})
    cached = tag_cache.get(tag, {})
    etag = cached.get("etag", "")

    headers: dict[str, str] = {}
    if etag:
        headers["If-None-Match"] = etag

    try:
        resp = client.get(f"/repos/{repo}/releases/tags/{tag}", headers=headers)
        if resp.status_code == 304:
            return cached.get("exists", False)
        exists = resp.status_code == 200
    except httpx.HTTPError:
        # Network error — use cached result if available
        return cached.get("exists", False)

    # Update cache
    tag_cache[tag] = {
        "etag": resp.headers.get("etag", ""),
        "exists": exists,
    }
    cache["tags_checked"] = tag_cache
    _save_cache(cache)
    return exists


def _next_page(link_header: str | None) -> str | None:
    """Extract the ``next`` URL from a GitHub ``Link`` header."""
    if not link_header:
        return None
    for part in link_header.split(","):
        if 'rel="next"' in part:
            url = part.split(";")[0].strip().strip("<>")
            return url
    return None
