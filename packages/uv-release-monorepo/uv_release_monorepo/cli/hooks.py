"""The ``uvr hooks`` command."""

from __future__ import annotations

import argparse
from pathlib import Path

from ._common import _HOOK_ALIASES, _fatal
from ._workflow_state import _get_workflow_state, _render_workflow


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
                raise ValueError(f"Position {pos} out of range (1\u2013{n + 1})")
            new = list(steps)
            new.insert(pos - 1, step)
            return new
        return steps + [step]

    if action == "remove":
        pos = int(kwargs["position"])  # type: ignore[arg-type]
        if n == 0:
            raise ValueError("No steps to remove.")
        if pos < 1 or pos > n:
            raise ValueError(f"Position {pos} out of range (1\u2013{n})")
        new = list(steps)
        del new[pos - 1]
        return new

    if action == "update":
        pos = int(kwargs["position"])  # type: ignore[arg-type]
        if n == 0:
            raise ValueError("No steps to update.")
        if pos < 1 or pos > n:
            raise ValueError(f"Position {pos} out of range (1\u2013{n})")
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

    all_hooks, config = _get_workflow_state(release_yml)
    steps = all_hooks[hook_key]

    do_add: bool = getattr(args, "do_add", False)
    do_insert: bool = getattr(args, "do_insert", False)
    do_set: bool = getattr(args, "do_set", False)
    do_remove: bool = getattr(args, "do_remove", False)
    do_clear: bool = getattr(args, "do_clear", False)
    position: int | None = getattr(args, "position", None)

    is_mutation = do_add or do_insert or do_set or do_remove or do_clear

    if not is_mutation:
        # Read mode — list steps
        if not steps:
            print(f"{hook_display}: no steps configured.")
        else:
            for i, step in enumerate(steps, 1):
                name = step.get("name") or step.get("uses") or step.get("run", "")[:40]
                print(f"  {i}. {name}")
        return

    if do_clear:
        all_hooks[hook_key] = []
        print(f"Cleared all steps from {hook_display}.")
    elif do_add:
        step_kw = _step_kwargs_from_args(args)
        step_id = step_kw.get("id")
        if step_id:
            # Upsert by --id
            for i, s in enumerate(steps):
                if s.get("id") == step_id:
                    steps[i] = _hooks_apply([s], "update", position=1, **step_kw)[0]
                    print(f"Updated step '{step_id}' in {hook_display}.")
                    break
            else:
                all_hooks[hook_key] = _hooks_apply(steps, "add", **step_kw)
                print(f"Added step to {hook_display}.")
        else:
            all_hooks[hook_key] = _hooks_apply(steps, "add", **step_kw)
            print(f"Added step to {hook_display}.")
    elif do_insert:
        if position is None:
            _fatal("--insert requires --at INDEX")
        step_kw = _step_kwargs_from_args(args)
        try:
            all_hooks[hook_key] = _hooks_apply(
                steps, "insert", position=position, **step_kw
            )
            print(f"Inserted step at position {position} in {hook_display}.")
        except ValueError as e:
            _fatal(str(e))
    elif do_set:
        if position is None:
            _fatal("--set requires --at INDEX")
        step_kw = _step_kwargs_from_args(args)
        try:
            all_hooks[hook_key] = _hooks_apply(
                steps, "update", position=position, **step_kw
            )
            print(f"Updated step at position {position} in {hook_display}.")
        except ValueError as e:
            _fatal(str(e))
    elif do_remove:
        if position is None:
            _fatal("--remove requires --at INDEX")
        try:
            all_hooks[hook_key] = _hooks_apply(steps, "remove", position=position)
            print(f"Removed step at position {position} from {hook_display}.")
        except ValueError as e:
            _fatal(str(e))

    _render_workflow(release_yml, all_hooks, config)
    print(f"Re-rendered {release_yml.relative_to(root)}")
