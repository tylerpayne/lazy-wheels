"""Tests for the hook system."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from uv_release_monorepo.shared.hooks import ReleaseHook, load_hook
from uv_release_monorepo.shared.models import PlanConfig, ReleasePlan

from tests._helpers import _make_plan


# -- ReleaseHook base class -------------------------------------------------


class TestReleaseHookBase:
    def test_post_plan_returns_plan_unchanged(self) -> None:
        hook = ReleaseHook()
        plan = _make_plan(changed=["pkg-alpha"])
        assert hook.post_plan(plan) is plan

    def test_pre_plan_returns_config_unchanged(self) -> None:
        hook = ReleaseHook()
        config = PlanConfig(
            rebuild_all=False,
            matrix={},
            uvr_version="0.1.0",
        )
        assert hook.pre_plan(config) is config

    def test_ci_hooks_are_noop(self) -> None:
        hook = ReleaseHook()
        plan = _make_plan(changed=["pkg-alpha"])
        # All CI hooks should be callable and return None
        assert hook.pre_build(plan) is None
        assert hook.post_build(plan) is None
        assert hook.pre_release(plan) is None
        assert hook.post_release(plan) is None
        assert hook.pre_bump(plan) is None
        assert hook.post_bump(plan) is None


# -- load_hook ---------------------------------------------------------------


def _write_hook_file(path: Path, body: str) -> None:
    """Write a Python hook module at *path*."""
    path.write_text(textwrap.dedent(body))


class TestLoadHook:
    def test_returns_none_when_no_config_and_no_convention(
        self, tmp_path: Path
    ) -> None:
        assert load_hook(tmp_path, {}) is None

    def test_convention_file_discovery(self, tmp_path: Path) -> None:
        _write_hook_file(
            tmp_path / "uvr_hooks.py",
            """\
            from uv_release_monorepo.shared.hooks import ReleaseHook

            class Hook(ReleaseHook):
                pass
            """,
        )
        hook = load_hook(tmp_path, {})
        assert hook is not None
        assert isinstance(hook, ReleaseHook)

    def test_explicit_config_with_class_name(self, tmp_path: Path) -> None:
        _write_hook_file(
            tmp_path / "my_hooks.py",
            """\
            from uv_release_monorepo.shared.hooks import ReleaseHook

            class MyHook(ReleaseHook):
                pass
            """,
        )
        hook = load_hook(tmp_path, {"file": "my_hooks.py:MyHook"})
        assert hook is not None
        assert isinstance(hook, ReleaseHook)

    def test_explicit_config_defaults_class_to_hook(self, tmp_path: Path) -> None:
        _write_hook_file(
            tmp_path / "hooks.py",
            """\
            from uv_release_monorepo.shared.hooks import ReleaseHook

            class Hook(ReleaseHook):
                pass
            """,
        )
        hook = load_hook(tmp_path, {"file": "hooks.py"})
        assert hook is not None

    def test_explicit_config_file_not_found_exits(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit):
            load_hook(tmp_path, {"file": "nonexistent.py"})

    def test_missing_class_exits(self, tmp_path: Path) -> None:
        _write_hook_file(
            tmp_path / "hooks.py",
            """\
            from uv_release_monorepo.shared.hooks import ReleaseHook

            class WrongName(ReleaseHook):
                pass
            """,
        )
        with pytest.raises(SystemExit):
            load_hook(tmp_path, {"file": "hooks.py:Missing"})

    def test_not_a_subclass_exits(self, tmp_path: Path) -> None:
        _write_hook_file(
            tmp_path / "hooks.py",
            """\
            class Hook:
                pass
            """,
        )
        with pytest.raises(SystemExit):
            load_hook(tmp_path, {"file": "hooks.py"})


# -- Hook behaviour ----------------------------------------------------------


class TestHookBehaviour:
    def test_post_plan_can_add_extra_keys(self, tmp_path: Path) -> None:
        _write_hook_file(
            tmp_path / "uvr_hooks.py",
            """\
            from uv_release_monorepo.shared.hooks import ReleaseHook
            from uv_release_monorepo.shared.models import ReleasePlan

            class Hook(ReleaseHook):
                def post_plan(self, plan: ReleasePlan) -> ReleasePlan:
                    data = plan.model_dump()
                    data["deploy_env"] = "staging"
                    return ReleasePlan.model_validate(data)
            """,
        )
        hook = load_hook(tmp_path, {})
        assert hook is not None

        plan = _make_plan(changed=["pkg-alpha"])
        modified = hook.post_plan(plan)
        assert modified.model_extra is not None
        assert modified.model_extra["deploy_env"] == "staging"

    def test_pre_plan_can_modify_config(self, tmp_path: Path) -> None:
        _write_hook_file(
            tmp_path / "uvr_hooks.py",
            """\
            from uv_release_monorepo.shared.hooks import ReleaseHook
            from uv_release_monorepo.shared.models import PlanConfig

            class Hook(ReleaseHook):
                def pre_plan(self, config: PlanConfig) -> PlanConfig:
                    config.rebuild_all = True
                    return config
            """,
        )
        hook = load_hook(tmp_path, {})
        assert hook is not None

        config = PlanConfig(rebuild_all=False, matrix={}, uvr_version="0.1.0")
        modified = hook.pre_plan(config)
        assert modified.rebuild_all is True

    def test_extra_keys_survive_json_round_trip(self, tmp_path: Path) -> None:
        _write_hook_file(
            tmp_path / "uvr_hooks.py",
            """\
            from uv_release_monorepo.shared.hooks import ReleaseHook
            from uv_release_monorepo.shared.models import ReleasePlan

            class Hook(ReleaseHook):
                def post_plan(self, plan: ReleasePlan) -> ReleasePlan:
                    data = plan.model_dump()
                    data["custom_flags"] = {"notify": True, "env": "prod"}
                    return ReleasePlan.model_validate(data)
            """,
        )
        hook = load_hook(tmp_path, {})
        assert hook is not None

        plan = _make_plan(changed=["pkg-alpha"])
        modified = hook.post_plan(plan)

        # JSON round-trip
        json_str = modified.model_dump_json()
        restored = ReleasePlan.model_validate_json(json_str)
        assert restored.model_extra is not None
        assert restored.model_extra["custom_flags"] == {"notify": True, "env": "prod"}
