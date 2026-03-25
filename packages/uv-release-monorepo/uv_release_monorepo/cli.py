"""CLI entry point for uv-release-monorepo."""

from __future__ import annotations

import argparse
import json
import sys
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import NoReturn

from .pipeline import build_plan, execute_plan
from .toml import (
    get_uvr_matrix,
    load_pyproject,
    save_pyproject,
    set_uvr_matrix,
)
from .workflow_steps import run_pipeline

__version__ = pkg_version("uv-release-monorepo")
TEMPLATES_DIR = Path(__file__).parent / "templates"
_VALID_HOOKS = ("pre_build", "post_build", "pre_release", "post_release")
_HOOK_ALIASES = {
    "pre-build": "pre_build",
    "post-build": "post_build",
    "pre-release": "pre_release",
    "post-release": "post_release",
    "pre_build": "pre_build",
    "post_build": "post_build",
    "pre_release": "pre_release",
    "post_release": "post_release",
}


def _read_matrix(root: Path) -> dict[str, list[str]]:
    """Read [tool.uvr.matrix] from the workspace pyproject.toml."""
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return {}
    return get_uvr_matrix(load_pyproject(pyproject))


def _print_matrix_status(package_runners: dict[str, list[str]]) -> None:
    """Print each package's build runners as a list."""
    if not package_runners:
        return

    names = sorted(package_runners.keys())
    w = max(len(n) for n in names)

    print()
    print("Build matrix:")
    for pkg in names:
        runners = package_runners[pkg]
        print(f"  {pkg.ljust(w)}  \u2192  {', '.join(runners)}")


def _discover_packages(root: Path | None = None) -> dict[str, tuple[str, list[str]]]:
    """Scan workspace members and return {name: (version, [internal_dep_names])}.

    Lightweight alternative to pipeline.discover_packages() — no git or
    shell calls, no stdout output.

    Args:
        root: Workspace root directory. Defaults to the current working directory.
    """
    import glob as globmod

    import tomlkit
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    root = root or Path.cwd()
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return {}

    doc = tomlkit.parse(pyproject.read_text())
    member_globs = (
        doc.get("tool", {}).get("uv", {}).get("workspace", {}).get("members", [])
    )

    # First pass: collect names, versions, and raw dependency strings
    packages: dict[str, tuple[str, list[str]]] = {}
    raw_deps: dict[str, list[str]] = {}
    for pattern in member_globs:
        for match in sorted(globmod.glob(str(root / pattern))):
            p = Path(match)
            pkg_toml = p / "pyproject.toml"
            if pkg_toml.exists():
                pkg_doc = tomlkit.parse(pkg_toml.read_text())
                raw_name = pkg_doc.get("project", {}).get("name", p.name)
                name = canonicalize_name(raw_name)
                version = pkg_doc.get("project", {}).get("version", "0.0.0")
                packages[name] = (version, [])
                # Gather all dependency strings
                dep_strs = list(pkg_doc.get("project", {}).get("dependencies", []))
                for group in (
                    pkg_doc.get("project", {}).get("optional-dependencies", {}).values()
                ):
                    dep_strs.extend(group)
                for group in pkg_doc.get("dependency-groups", {}).values():
                    dep_strs.extend(s for s in group if isinstance(s, str))
                raw_deps[name] = dep_strs

    # Apply include/exclude filters from [tool.uvr.config]
    uvr_config = doc.get("tool", {}).get("uvr", {}).get("config", {})
    include = list(uvr_config.get("include", []))
    exclude = list(uvr_config.get("exclude", []))
    if include:
        packages = {n: p for n, p in packages.items() if n in include}
        raw_deps = {n: d for n, d in raw_deps.items() if n in packages}
    if exclude:
        for name in exclude:
            packages.pop(name, None)
            raw_deps.pop(name, None)

    # Second pass: resolve internal deps
    workspace_names = set(packages.keys())
    for name, dep_strs in raw_deps.items():
        for dep_str in dep_strs:
            try:
                dep_name = canonicalize_name(Requirement(dep_str).name)
            except Exception:
                continue
            if dep_name in workspace_names and dep_name != name:
                packages[name][1].append(dep_name)

    return packages


def _print_dependencies(
    packages: dict[str, tuple[str, list[str]]],
    *,
    direct_dirty: set[str] | None = None,
    transitive_dirty: set[str] | None = None,
) -> None:
    """Print each package's version and internal dependencies as a list."""
    if not packages:
        return

    direct_dirty = direct_dirty or set()
    transitive_dirty = transitive_dirty or set()
    names = sorted(packages.keys())
    w = max(len(n) for n in names)
    vw = max(len(packages[n][0]) for n in names)

    print()
    print("Dependencies:")
    for name in names:
        version, deps = packages[name]
        if name in direct_dirty:
            label = f"* {name}"
        elif name in transitive_dirty:
            label = f"+ {name}"
        else:
            label = f"  {name}"
        ver_col = version.ljust(vw)
        if deps:
            print(
                f"  {label.ljust(w + 2)}  {ver_col}  \u2192  {', '.join(sorted(deps))}"
            )
        else:
            print(f"  {label.ljust(w + 2)}  {ver_col}")
    has_direct = direct_dirty & set(names)
    has_transitive = transitive_dirty & set(names)
    if has_direct or has_transitive:
        print()
        if has_direct:
            print("  * = changed since last release")
        if has_transitive:
            print("  + = rebuild (dependency changed)")


def _discover_package_names() -> list[str]:
    """Scan workspace members and return sorted package names."""
    return sorted(_discover_packages().keys())


def _fatal(msg: str) -> NoReturn:
    """Print error and exit."""
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


def _empty_hooks() -> dict[str, list[dict]]:
    """Return an empty hooks dict with all four phases."""
    return {h: [] for h in _VALID_HOOKS}


def _get_hooks_from_workflow(path: Path) -> dict[str, list[dict]]:
    """Extract user-defined hook steps from a generated release.yml.

    Parses the YAML and looks for hook jobs (pre-build, post-build,
    pre-release, post-release). User steps are those after the
    "Export plan context" step.
    """
    import yaml

    hooks = _empty_hooks()
    if not path.exists():
        return hooks

    try:
        with open(path) as f:
            doc = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise SystemExit(
            f"error: {path} contains invalid YAML and cannot be parsed.\n"
            f"  {exc}\n\n"
            "Run `uvr init --force` to discard the existing file and regenerate."
        ) from None

    if not doc or "jobs" not in doc:
        return hooks

    jobs = doc["jobs"]
    job_to_hook = {
        "pre-build": "pre_build",
        "post-build": "post_build",
        "pre-release": "pre_release",
        "post-release": "post_release",
    }

    for job_name, hook_key in job_to_hook.items():
        job = jobs.get(job_name)
        if not job or "steps" not in job:
            continue
        steps = job["steps"]
        after_export = False
        for step in steps:
            if not isinstance(step, dict):
                continue
            if step.get("name") == "Export plan context":
                after_export = True
                continue
            if after_export:
                hooks[hook_key].append(dict(step))

    return hooks


def _step_to_yaml(step: dict) -> str:
    """Convert a step dict to YAML for embedding in the workflow template.

    Returns the YAML mapping body (no leading ``- ``). The caller or
    Jinja2 ``indent`` filter handles indentation of continuation lines.
    """
    import yaml

    class _Dumper(yaml.SafeDumper):
        pass

    def _str_representer(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
        if "\n" in data:
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
        return dumper.represent_scalar("tag:yaml.org,2002:str", data)

    _Dumper.add_representer(str, _str_representer)

    result = yaml.dump(step, Dumper=_Dumper, default_flow_style=False, sort_keys=False)
    return result.rstrip("\n")


def _render_workflow(dest: Path, hooks: dict[str, list[dict]]) -> None:
    """Render the Jinja2 template with hook config and write to dest."""
    import jinja2

    template_env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
        variable_start_string="[[",
        variable_end_string="]]",
        block_start_string="[%",
        block_end_string="%]",
        comment_start_string="[#",
        comment_end_string="#]",
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    template_env.filters["step_yaml"] = _step_to_yaml
    rendered = template_env.get_template("release.yml.j2").render(hooks=hooks)
    dest.write_text(rendered)


def cmd_init(args: argparse.Namespace) -> None:
    """Scaffold the GitHub Actions workflow into your repo."""
    root = Path.cwd()

    # Sanity checks
    if not (root / ".git").exists():
        _fatal("Not a git repository. Run from the repo root.")

    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        _fatal("No pyproject.toml found in current directory.")

    doc = load_pyproject(pyproject)
    members = doc.get("tool", {}).get("uv", {}).get("workspace", {}).get("members")
    if not members:
        _fatal(
            "No [tool.uv.workspace] members defined in pyproject.toml.\n"
            "uvr requires a uv workspace. Example:\n\n"
            "  [tool.uv.workspace]\n"
            '  members = ["packages/*"]'
        )

    # Write workflow
    dest_dir = root / args.workflow_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "release.yml"

    # Start with existing matrix entries (additive)
    package_runners = _read_matrix(root)

    # Overlay new -m entries (replace per-package)
    if args.matrix:
        for entry in args.matrix:
            if len(entry) < 2:
                _fatal(
                    f"Invalid -m: need PKG and at least one runner, got: {' '.join(entry)}"
                )
            package, *runners = entry
            package_runners[package] = runners

    # Write matrix config to pyproject.toml
    set_uvr_matrix(doc, package_runners)
    save_pyproject(pyproject, doc)

    # Render and write workflow template, preserving existing hooks
    force = getattr(args, "force", False)
    if dest.exists() and not force:
        hooks = _get_hooks_from_workflow(dest)
    else:
        hooks = _empty_hooks()
    _render_workflow(dest, hooks)

    print(f"\u2713 Wrote workflow to {dest.relative_to(root)}")
    _print_matrix_status(package_runners)
    print()
    print("Next steps:")
    print("  1. Commit and push the workflow file")
    print("  2. Trigger a release:")
    print("       uvr release")
    print("       uvr release --rebuild-all")


def cmd_run(args: argparse.Namespace) -> None:
    """Run the release pipeline locally (usually called from CI)."""
    if getattr(args, "plan", None):
        from uv_release_monorepo.models import ReleasePlan

        plan = ReleasePlan.model_validate_json(args.plan)
        execute_plan(plan, push=not args.no_push)
    else:
        run_pipeline(
            rebuild_all=args.rebuild_all,
            push=not args.no_push,
            dry_run=args.dry_run,
        )


def cmd_release(args: argparse.Namespace) -> None:
    """Generate a release plan and optionally dispatch the executor workflow."""
    root = Path.cwd()
    workflow_path = root / args.workflow_dir / "release.yml"
    if not workflow_path.exists():
        _fatal("No release workflow found. Run `uvr init` first.")

    # Read stored matrix from pyproject.toml
    package_runners = _read_matrix(root)

    # Build the plan locally (runs discovery + change detection + pin updates)
    plan, pin_updates = build_plan(
        rebuild_all=args.rebuild_all,
        matrix=package_runners,
        uvr_version=__version__,
        python_version=args.python_version,
    )

    if pin_updates:
        print()
        print("Dep pins updated — commit these changes before releasing:")
        for name in pin_updates:
            print(f"  git add {plan.changed[name].path}/pyproject.toml")
        print("  git commit -m 'chore: update dep pins'")
        print("  git push")
        print("  uvr release")
        return

    if not plan.changed:
        print("Nothing changed since last release. Use --rebuild-all to rebuild all.")
        return

    # Print the plan
    print(json.dumps(plan.model_dump(), indent=2))

    # Prompt for confirmation before dispatching (skip with --yes)
    if not args.yes:
        try:
            answer = input("\nDispatch release? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if answer != "y":
            return

    # Dispatch via gh
    import subprocess
    import time

    plan_json = plan.model_dump_json()
    cmd = [
        "gh",
        "workflow",
        "run",
        "release.yml",
        "-f",
        f"plan={plan_json}",
        "-f",
        f"uvr_version={__version__}",
    ]
    print(f"Triggering release for: {', '.join(sorted(plan.changed))}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        _fatal("Failed to trigger workflow")

    # Wait for the run to be created and fetch its URL
    print("Waiting for workflow run...")
    time.sleep(2)

    result = subprocess.run(
        [
            "gh",
            "run",
            "list",
            "--workflow=release.yml",
            "--limit=1",
            "--json=url,status",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout:
        try:
            runs = json.loads(result.stdout)
            if runs:
                url = runs[0].get("url", "")
                status = runs[0].get("status", "")
                print(f"Status: {status}")
                print(f"Watch:  {url}")
        except json.JSONDecodeError:
            pass


def cmd_status(args: argparse.Namespace) -> None:
    """Show the current workflow configuration."""
    from uv_release_monorepo.pipeline import (
        detect_changes,
        discover_packages,
        find_dev_baselines,
    )

    root = Path.cwd()
    dest = root / args.workflow_dir / "release.yml"

    if not dest.exists():
        print("No release workflow found.")
        print("Run `uvr init` to create one.")
        return

    package_runners = _read_matrix(root)
    packages = _discover_packages()
    if not package_runners:
        if packages:
            package_runners = {pkg: ["ubuntu-latest"] for pkg in packages}

    # Detect dirty packages using the pipeline's logic (suppress verbose output)
    import io

    direct_dirty: set[str] = set()
    transitive_dirty: set[str] = set()
    try:
        old_stdout = sys.stdout
        captured = io.StringIO()
        sys.stdout = captured
        try:
            pipeline_pkgs = discover_packages()
            dev_baselines = find_dev_baselines(pipeline_pkgs)
            all_dirty = set(
                detect_changes(pipeline_pkgs, dev_baselines, rebuild_all=False)
            )
        finally:
            sys.stdout = old_stdout

        # Parse captured output to distinguish direct vs transitive
        for line in captured.getvalue().splitlines():
            stripped = line.strip()
            if "dirty (depends on" in stripped:
                pkg_name = stripped.split(":")[0]
                transitive_dirty.add(pkg_name)
        direct_dirty = all_dirty - transitive_dirty
    except (SystemExit, Exception):
        pass  # Non-fatal — just skip dirty markers if detection fails

    _print_matrix_status(package_runners)
    _print_dependencies(
        packages, direct_dirty=direct_dirty, transitive_dirty=transitive_dirty
    )


def _parse_install_spec(spec: str) -> tuple[str | None, str, str | None]:
    """Parse an install spec into (gh_repo, package, version).

    Accepted forms:
      package[@version]              — local workspace package
      org/repo/package[@version]     — remote GitHub repo
    """
    version: str | None = None
    if "@" in spec:
        spec, version = spec.rsplit("@", 1)

    parts = spec.split("/")
    if len(parts) == 1:
        return None, parts[0], version
    elif len(parts) == 3:
        org, repo, package = parts
        return f"{org}/{repo}", package, version
    else:
        _fatal(
            f"Invalid install spec '{spec}'. "
            "Expected 'package' or 'org/repo/package', optionally with '@version'."
        )


def _find_latest_release_tag(package: str, gh_repo: str | None = None) -> str | None:
    """Return the most recent non-dev release tag for a package.

    Queries GitHub releases for tags matching {package}/v*, excludes -dev tags,
    and returns the one with the highest version number.
    """
    import subprocess

    from packaging.version import Version

    cmd = ["gh", "release", "list", "--json", "tagName", "--limit", "200"]
    if gh_repo:
        cmd.extend(["--repo", gh_repo])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        releases = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    prefix = f"{package}/v"
    tags = [
        r["tagName"]
        for r in releases
        if r["tagName"].startswith(prefix) and not r["tagName"].endswith("-dev")
    ]
    if not tags:
        return None
    return max(tags, key=lambda t: Version(t.split("/v")[-1]))


def cmd_install(args: argparse.Namespace) -> None:
    """Install a package and its transitive internal deps from GitHub releases."""
    import subprocess
    import tempfile

    gh_repo, package, version = _parse_install_spec(args.package)

    if gh_repo is None:
        # Local workspace: resolve transitive internal deps via workspace graph
        packages = _discover_packages()
        if package not in packages:
            _fatal(f"Package '{package}' not found in workspace.")

        order: list[str] = []
        visited: set[str] = set()
        stack = [package]
        while stack:
            pkg = stack.pop()
            if pkg in visited:
                continue
            visited.add(pkg)
            order.append(pkg)
            for dep in packages[pkg][1]:
                if dep not in visited:
                    stack.append(dep)
        order.reverse()  # deps before dependents
    else:
        # Remote: install only the requested package; pip resolves external deps
        order = [package]

    with tempfile.TemporaryDirectory() as tmp:
        wheels: list[str] = []
        for pkg in order:
            if pkg == package and version:
                tag = f"{pkg}/v{version}"
            else:
                tag = _find_latest_release_tag(pkg, gh_repo=gh_repo)
            if not tag:
                _fatal(f"No release found for '{pkg}'.")

            cmd = [
                "gh",
                "release",
                "download",
                tag,
                "--pattern",
                "*.whl",
                "--dir",
                tmp,
                "--clobber",
            ]
            if gh_repo:
                cmd.extend(["--repo", gh_repo])

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                _fatal(f"Failed to download release {tag}: {result.stderr.strip()}")

            found = list(Path(tmp).glob(f"{pkg.replace('-', '_')}-*.whl"))
            if not found:
                _fatal(f"No wheel found for '{pkg}' in release {tag}.")
            wheels.append(str(found[0]))
            print(f"  {found[0].name}")

        print(f"\nInstalling {len(wheels)} wheel(s)...")
        subprocess.run(["uv", "pip", "install", *wheels], check=True)


def _hooks_show(steps: list[dict], hook_display: str) -> None:
    """Print a numbered list of hook steps."""
    n = len(steps)
    if n == 0:
        print(f"{hook_display}: (no steps)")
        return
    print(f"{hook_display} ({n} step{'s' if n != 1 else ''}):")
    for i, step in enumerate(steps, 1):
        id_part = f" [{step['id']}]" if "id" in step else ""
        label = step.get("name") or step.get("uses") or step.get("run", "(unnamed)")
        print(f"  {i}.{id_part} {label}")
        if "run" in step and "name" in step:
            print(f"       run: {step['run']}")
        if "uses" in step:
            print(f"       uses: {step['uses']}")


def _hooks_apply(steps: list[dict], action: str, **kwargs: object) -> list[dict]:
    """Return a new step list after applying action. Raises ValueError on bad input."""
    n = len(steps)
    if action == "clear":
        return []

    if action in ("add", "insert"):
        step: dict = {}
        for key in ("id", "name", "uses", "run", "if", "with", "env"):
            val = kwargs.get(key)
            if val:
                step[key] = val
        if not step.get("run") and not step.get("uses"):
            raise ValueError("Step requires at least --run or --uses.")
        if action == "insert":
            pos = int(kwargs["position"])  # type: ignore[arg-type]
            if pos < 1 or pos > n + 1:
                raise ValueError(f"Position {pos} out of range (1–{n + 1})")
            new = list(steps)
            new.insert(pos - 1, step)
            return new
        return steps + [step]

    if action == "remove":
        pos = int(kwargs["position"])  # type: ignore[arg-type]
        if n == 0:
            raise ValueError("No steps to remove.")
        if pos < 1 or pos > n:
            raise ValueError(f"Position {pos} out of range (1–{n})")
        new = list(steps)
        del new[pos - 1]
        return new

    if action == "update":
        pos = int(kwargs["position"])  # type: ignore[arg-type]
        if n == 0:
            raise ValueError("No steps to update.")
        if pos < 1 or pos > n:
            raise ValueError(f"Position {pos} out of range (1–{n})")
        new = list(steps)
        step = dict(new[pos - 1])
        for key in ("id", "name", "uses", "run", "if", "with", "env"):
            val = kwargs.get(key)
            if val:
                step[key] = val
        new[pos - 1] = step
        return new

    raise ValueError(f"Unknown action: {action}")


def _hooks_interactive(hook_key: str, steps: list[dict]) -> list[dict]:
    """Prompt-based step editor. Returns the final step list."""
    hook_display = hook_key.replace("_", "-")
    print(f"Editing {hook_display} hooks. Type 'done' or press Ctrl-D to finish.")
    while True:
        print()
        _hooks_show(steps, hook_display)
        print()
        print(
            "  add | insert POSITION | remove POSITION | update POSITION | clear | done"
        )
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line or line == "done":
            break

        parts = line.split(None, 1)
        cmd = parts[0].lower()

        if cmd == "clear":
            steps = []
            print("Cleared.")
            continue

        if cmd == "add":
            try:
                name = input("  name (optional): ").strip()
                uses = input("  uses (optional): ").strip()
                run = input("  run  (optional): ").strip()
                step_id = input("  id   (optional): ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            try:
                steps = _hooks_apply(
                    steps,
                    "add",
                    name=name or None,
                    uses=uses or None,
                    run=run or None,
                    id=step_id or None,
                )
                print("Added step.")
            except ValueError as e:
                print(f"Error: {e}")
            continue

        if cmd in ("insert", "remove", "update"):
            if len(parts) < 2:
                print(f"Usage: {cmd} POSITION")
                continue
            try:
                pos = int(parts[1])
            except ValueError:
                print(f"Invalid position '{parts[1]}'")
                continue

            try:
                if cmd == "remove":
                    steps = _hooks_apply(steps, "remove", position=pos)
                    print(f"Removed step {pos}.")
                elif cmd == "insert":
                    name = input("  name (optional): ").strip()
                    uses = input("  uses (optional): ").strip()
                    run = input("  run  (optional): ").strip()
                    step_id = input("  id   (optional): ").strip()
                    steps = _hooks_apply(
                        steps,
                        "insert",
                        position=pos,
                        name=name or None,
                        uses=uses or None,
                        run=run or None,
                        id=step_id or None,
                    )
                    print(f"Inserted at position {pos}.")
                else:  # update
                    if 1 <= pos <= len(steps):
                        cur = steps[pos - 1]
                        for k, v in cur.items():
                            print(f"  Current {k}: {v}")
                    name = input("  name (Enter to keep): ").strip()
                    uses = input("  uses (Enter to keep): ").strip()
                    run = input("  run  (Enter to keep): ").strip()
                    step_id = input("  id   (Enter to keep): ").strip()
                    steps = _hooks_apply(
                        steps,
                        "update",
                        position=pos,
                        name=name or None,
                        uses=uses or None,
                        run=run or None,
                        id=step_id or None,
                    )
                    print(f"Updated step {pos}.")
            except (ValueError, EOFError, KeyboardInterrupt) as e:
                if isinstance(e, (EOFError, KeyboardInterrupt)):
                    print()
                    break
                print(f"Error: {e}")
            continue

        print(
            f"Unknown command '{cmd}'. Try: add | insert N | remove N | update N | clear | done"
        )

    return steps


def _parse_kv_pairs(pairs: list[str] | None) -> dict[str, str] | None:
    """Parse ['KEY=VALUE', ...] into a dict, or None if empty."""
    if not pairs:
        return None
    result: dict[str, str] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep:
            _fatal(f"Invalid key=value pair: {pair!r} (expected KEY=VALUE)")
        result[key] = value
    return result


def _step_kwargs_from_args(args: argparse.Namespace) -> dict[str, object]:
    """Extract step fields from parsed CLI args."""
    kw: dict[str, object] = {}
    for field in ("id", "name", "uses", "run"):
        val = getattr(args, field, None)
        if val:
            kw[field] = val
    step_if = getattr(args, "step_if", None)
    if step_if:
        kw["if"] = step_if
    step_with = _parse_kv_pairs(getattr(args, "step_with", None))
    if step_with:
        kw["with"] = step_with
    step_env = _parse_kv_pairs(getattr(args, "step_env", None))
    if step_env:
        kw["env"] = step_env
    return kw


def cmd_hooks(args: argparse.Namespace) -> None:
    """Manage CI hook steps in the release workflow."""
    root = Path.cwd()
    workflow_dir = getattr(args, "workflow_dir", ".github/workflows")
    release_yml = root / workflow_dir / "release.yml"
    if not release_yml.exists():
        _fatal("No release.yml found. Run `uvr init` first to generate the workflow.")

    hook_key = _HOOK_ALIASES[args.hook_point]
    hook_display = args.hook_point

    all_hooks = _get_hooks_from_workflow(release_yml)
    steps = all_hooks[hook_key]

    action = getattr(args, "hook_action", None)

    if action is None:
        # Interactive mode
        steps = _hooks_interactive(hook_key, steps)
        all_hooks[hook_key] = steps
    elif action == "clear":
        all_hooks[hook_key] = []
        print(f"Cleared all steps from {hook_display}.")
    elif action == "add":
        step_kw = _step_kwargs_from_args(args)
        if args.id:
            for i, s in enumerate(steps):
                if s.get("id") == args.id:
                    steps[i] = _hooks_apply([s], "update", position=1, **step_kw)[0]
                    print(f"Updated step '{args.id}' in {hook_display}.")
                    break
            else:
                all_hooks[hook_key] = _hooks_apply(steps, "add", **step_kw)
                print(f"Added step to {hook_display}.")
        else:
            all_hooks[hook_key] = _hooks_apply(steps, "add", **step_kw)
            print(f"Added step to {hook_display}.")
    else:
        try:
            step_kw = _step_kwargs_from_args(args)
            step_kw["position"] = args.position
            all_hooks[hook_key] = _hooks_apply(steps, action, **step_kw)
            print("Done.")
        except ValueError as e:
            _fatal(str(e))

    _render_workflow(release_yml, all_hooks)
    print(f"Re-rendered {release_yml.relative_to(root)}")


def cli() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="uvr",
        description="Lazy monorepo wheel builder — only rebuilds what changed.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # init subcommand
    init_parser = subparsers.add_parser(
        "init", help="Scaffold the GitHub Actions workflow into your repo."
    )
    init_parser.add_argument(
        "--workflow-dir",
        default=".github/workflows",
        help="Directory to write the workflow file. (default: %(default)s)",
    )
    init_parser.add_argument(
        "-m",
        "--matrix",
        nargs="+",
        action="append",
        metavar="PKG RUNNER",
        help="Per-package runners: -m PKG runner1 runner2 (repeatable).",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite release.yml without preserving existing hooks.",
    )
    init_parser.set_defaults(func=cmd_init)

    # run subcommand
    run_parser = subparsers.add_parser(
        "run", help="Run the release pipeline locally (usually called from CI)."
    )
    run_parser.add_argument(
        "--rebuild-all", action="store_true", help="Rebuild all packages."
    )
    run_parser.add_argument(
        "--no-push",
        action="store_true",
        help="Skip git push (useful when workflow handles push separately).",
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be released without making any changes.",
    )
    run_parser.add_argument(
        "--plan",
        default=None,
        help="Execute a pre-computed release plan JSON instead of running discovery.",
    )
    run_parser.set_defaults(func=cmd_run)

    # release subcommand
    release_parser = subparsers.add_parser(
        "release",
        help="Generate a release plan locally and dispatch the executor workflow.",
    )
    release_parser.add_argument(
        "--rebuild-all", action="store_true", help="Rebuild all packages."
    )
    release_parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip confirmation prompt and dispatch immediately.",
    )
    release_parser.add_argument(
        "--python",
        default="3.12",
        metavar="VERSION",
        dest="python_version",
        help="Python version for CI builds. (default: %(default)s)",
    )
    release_parser.add_argument(
        "--workflow-dir",
        default=".github/workflows",
        help="Directory containing the workflow file. (default: %(default)s)",
    )
    release_parser.set_defaults(func=cmd_release)

    # status subcommand
    status_parser = subparsers.add_parser(
        "status", help="Show the current workflow configuration."
    )
    status_parser.add_argument(
        "--workflow-dir",
        default=".github/workflows",
        help="Directory containing the workflow file. (default: %(default)s)",
    )
    status_parser.set_defaults(func=cmd_status)

    # hooks subcommand — uvr hooks PHASE [ACTION ...]
    hooks_parser = subparsers.add_parser(
        "hooks",
        help="Manage CI hook steps in the release workflow.",
    )
    hooks_parser.add_argument(
        "--workflow-dir",
        default=".github/workflows",
        help="Directory containing the workflow file. (default: %(default)s)",
    )
    phase_subparsers = hooks_parser.add_subparsers(dest="hook_point")

    _PHASE_CHOICES = [
        ("pre-build", "Steps that run before the build job."),
        ("post-build", "Steps that run after the build job."),
        ("pre-release", "Steps that run before the release job."),
        ("post-release", "Steps that run after the release job."),
    ]

    def _add_step_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--name", help="Step display name.")
        p.add_argument("--run", help="Shell command to run.")
        p.add_argument("--uses", help="Action to use (e.g. actions/checkout@v4).")
        p.add_argument(
            "--with",
            dest="step_with",
            action="append",
            metavar="KEY=VALUE",
            help="Action input (repeatable).",
        )
        p.add_argument(
            "--env",
            dest="step_env",
            action="append",
            metavar="KEY=VALUE",
            help="Environment variable (repeatable).",
        )
        p.add_argument("--if", dest="step_if", help="Conditional expression.")
        p.add_argument("--id", help="Unique id for upsert semantics.")

    for _phase_name, _phase_help in _PHASE_CHOICES:
        _phase_parser = phase_subparsers.add_parser(_phase_name, help=_phase_help)
        _phase_parser.set_defaults(
            func=cmd_hooks, hook_point=_phase_name, hook_action=None
        )

        _action_subs = _phase_parser.add_subparsers(dest="hook_action")

        # clear
        _action_subs.add_parser("clear", help="Remove all steps.")

        # add (appends, or upserts by --id)
        _add_p = _action_subs.add_parser(
            "add", help="Append a step (upsert if --id matches)."
        )
        _add_step_args(_add_p)

        # insert POSITION
        _ins_p = _action_subs.add_parser(
            "insert", help="Insert a step at POSITION (1-indexed)."
        )
        _ins_p.add_argument("position", type=int, metavar="POSITION")
        _add_step_args(_ins_p)

        # remove POSITION
        _rm_p = _action_subs.add_parser(
            "remove", help="Remove the step at POSITION (1-indexed)."
        )
        _rm_p.add_argument("position", type=int, metavar="POSITION")

        # update POSITION
        _upd_p = _action_subs.add_parser(
            "update", help="Update the step at POSITION (1-indexed)."
        )
        _upd_p.add_argument("position", type=int, metavar="POSITION")
        _add_step_args(_upd_p)

        for _sub in _action_subs.choices.values():
            _sub.set_defaults(func=cmd_hooks, hook_point=_phase_name)

    hooks_parser.set_defaults(func=lambda _: hooks_parser.print_help())

    # install subcommand
    install_parser = subparsers.add_parser(
        "install",
        help="Install a workspace package and its internal deps from GitHub releases.",
    )
    install_parser.add_argument(
        "package",
        help="Package name, optionally pinned: PACKAGE[@VERSION]",
    )
    install_parser.set_defaults(func=cmd_install)

    args = parser.parse_args()
    args.func(args)
