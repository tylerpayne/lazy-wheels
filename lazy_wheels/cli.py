"""CLI entry point for lazy-wheels."""

from __future__ import annotations

from pathlib import Path

import click

from lazy_wheels.pipeline import run_release


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
def init(workflow_dir: str) -> None:
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

    template = Path(__file__).parent / "templates" / "release.yml"
    dest.write_text(template.read_text())

    click.echo(f"✓ Wrote workflow to {dest.relative_to(root)}")
    click.echo()
    click.echo("Next steps:")
    click.echo("  1. Commit and push the workflow file")
    click.echo("  2. Trigger a release:")
    click.echo("       gh workflow run release.yml")
    click.echo("       gh workflow run release.yml -f force_rebuild_all=true")


@cli.command()
@click.option("--force-all", is_flag=True, help="Rebuild all packages.")
def release(force_all: bool) -> None:
    """Run the release pipeline (usually called from CI)."""
    run_release(force_all=force_all)
