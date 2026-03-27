"""GitHub API client using httpx with connection reuse."""

from __future__ import annotations

import os
import re
import subprocess

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


def list_release_tag_names() -> set[str]:
    """Fetch all GitHub release tag names for the current repo.

    Paginates automatically. Returns an empty set on auth or network failure.
    """
    client = _get_client()
    repo = _get_repo()
    if not client or not repo:
        return set()

    tag_names: set[str] = set()
    url = f"/repos/{repo}/releases?per_page=100"

    while url:
        try:
            resp = client.get(url)
            resp.raise_for_status()
            for release in resp.json():
                tag_names.add(release["tag_name"])
            url = _next_page(resp.headers.get("link"))
        except (httpx.HTTPError, KeyError):
            break

    return tag_names


def _next_page(link_header: str | None) -> str | None:
    """Extract the ``next`` URL from a GitHub ``Link`` header."""
    if not link_header:
        return None
    for part in link_header.split(","):
        if 'rel="next"' in part:
            url = part.split(";")[0].strip().strip("<>")
            return url
    return None
