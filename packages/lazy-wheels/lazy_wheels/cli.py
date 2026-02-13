"""CLI entry point for lazy-wheels."""

from __future__ import annotations

from pathlib import Path

import click

from lazy_wheels.pipeline import discover_packages, run_release

DEFAULT_RUNNER = "ubuntu-latest"


def _matrix_include_lines(package_runners: dict[str, list[str]]) -> str:
    lines: list[str] = []
    for package, runners in package_runners.items():
        for runner in runners:
            lines.append(f'          - package: "{package}"')
            lines.append(f'            runner: "{runner}"')
    return "\n".join(lines)


@click.group()
@click.version_option()
def cli() -> None:
    """Lazy monorepo wheel builder — only rebuilds what changed."""


@cli.command()
@click.option(
    "--workflow-dir",
    type=click.Path(),
    default=".github/workflows",
    show_default=True,
    help="Directory to write the workflow file.",
)
@click.option(
    "--matrix-builder",
    is_flag=True,
    help="Interactively build a multi-job workflow with per-package runners.",
)
def init(workflow_dir: str, matrix_builder: bool) -> None:
    """Scaffold the GitHub Actions workflow into your repo."""
    root = Path.cwd()

    # Sanity checks
    if not (root / ".git").exists():
        raise click.ClickException("Not a git repository. Run from the repo root.")

    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        raise click.ClickException("No pyproject.toml found in current directory.")

    import tomlkit

    doc = tomlkit.parse(pyproject.read_text())
    members = doc.get("tool", {}).get("uv", {}).get("workspace", {}).get("members")
    if not members:
        raise click.ClickException(
            "No [tool.uv.workspace] members defined in pyproject.toml.\n"
            "lazy-wheels requires a uv workspace. Example:\n\n"
            "  [tool.uv.workspace]\n"
            '  members = ["packages/*"]'
        )

    # Write workflow
    dest_dir = root / workflow_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "release.yml"

    if matrix_builder:
        package_runners: dict[str, list[str]] = {}
        click.echo("Configure build runners for each package:")
        for package in sorted(discover_packages()):
            runners = click.prompt(
                f"  {package} runners (comma-separated)",
                default=DEFAULT_RUNNER,
                show_default=True,
            )
            selected_runners = [r.strip() for r in runners.split(",") if r.strip()]
            package_runners[package] = selected_runners or [DEFAULT_RUNNER]

        template = Path(__file__).parent / "release-matrix.yml"
        rendered = template.read_text().replace(
            "__MATRIX_INCLUDE__", _matrix_include_lines(package_runners)
        )
        dest.write_text(rendered)
    else:
        template = Path(__file__).parent / "release.yml"
        dest.write_text(template.read_text())

    click.echo(f"✓ Wrote workflow to {dest.relative_to(root)}")
    click.echo()
    click.echo("Next steps:")
    click.echo("  1. Commit and push the workflow file")
    click.echo("  2. Trigger a release:")
    click.echo("       lazy-wheels release")
    click.echo("       lazy-wheels release -r r1")
    click.echo("       lazy-wheels release --force-all")


@cli.command()
@click.option(
    "--release",
    "-r",
    default=None,
    help="Release tag (e.g., r1, r2). Auto-generates if not provided.",
)
@click.option("--force-all", is_flag=True, help="Rebuild all packages.")
def run(release: str | None, force_all: bool) -> None:
    """Run the release pipeline locally (usually called from CI)."""
    run_release(release=release, force_all=force_all)


@cli.command()
@click.option(
    "--release",
    "-r",
    default=None,
    help="Release tag (e.g., r1, r2). Auto-generates if not provided.",
)
@click.option("--force-all", is_flag=True, help="Force rebuild all packages.")
def release(release: str | None, force_all: bool) -> None:
    """Trigger a release via GitHub Actions workflow."""
    import json
    import subprocess
    import time

    cmd = ["gh", "workflow", "run", "release.yml"]
    if release:
        cmd.extend(["-f", f"release={release}"])
    if force_all:
        cmd.extend(["-f", "force_rebuild_all=true"])

    click.echo(f"Triggering: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise click.ClickException("Failed to trigger workflow")

    # Wait for the run to be created and fetch its URL
    click.echo("Waiting for workflow run...")
    time.sleep(2)

    result = subprocess.run(
        ["gh", "run", "list", "--workflow=release.yml", "--limit=1", "--json=url,status"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout:
        try:
            runs = json.loads(result.stdout)
            if runs:
                url = runs[0].get("url", "")
                status = runs[0].get("status", "")
                click.echo(f"Status: {status}")
                click.echo(f"Watch:  {url}")
        except json.JSONDecodeError:
            pass
