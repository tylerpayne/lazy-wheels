"""Tests for frozen entity types and VERSION parsing."""

from __future__ import annotations

from typing import Any

import pytest

from uv_release.types import (
    BumpType,
    Change,
    Config,
    Job,
    MergeResult,
    Package,
    Plan,
    PlanParams,
    Publishing,
    Release,
    Tag,
    Version,
    VersionState,
    Workflow,
    Workspace,
)


# ---------------------------------------------------------------------------
# VERSION parsing: parametrize all 11 VersionState variants
# ---------------------------------------------------------------------------

# fmt: off
_VERSION_MATRIX: list[tuple[str, VersionState, str, bool, int | None, str | None, int | None, int | None]] = [
    # (raw, expected_state, base, is_dev, dev_number, pre_kind, pre_number, post_number)

    # Stable
    ("1.0.1",              VersionState.CLEAN_STABLE,  "1.0.1", False, None, None, None, None),
    ("2.0.0",              VersionState.CLEAN_STABLE,  "2.0.0", False, None, None, None, None),
    ("0.1.0",              VersionState.CLEAN_STABLE,  "0.1.0", False, None, None, None, None),
    ("1.0.1.dev0",         VersionState.DEV0_STABLE,   "1.0.1", True,  0,    None, None, None),
    ("2.0.0.dev0",         VersionState.DEV0_STABLE,   "2.0.0", True,  0,    None, None, None),
    ("1.0.1.dev3",         VersionState.DEVK_STABLE,   "1.0.1", True,  3,    None, None, None),
    ("1.0.1.dev17",        VersionState.DEVK_STABLE,   "1.0.1", True,  17,   None, None, None),

    # Pre-release: alpha
    ("1.0.1a0",            VersionState.CLEAN_PRE0,    "1.0.1", False, None, "a",  0,    None),
    ("1.0.1b0",            VersionState.CLEAN_PRE0,    "1.0.1", False, None, "b",  0,    None),
    ("1.0.1rc0",           VersionState.CLEAN_PRE0,    "1.0.1", False, None, "rc", 0,    None),
    ("1.0.1a2",            VersionState.CLEAN_PREN,    "1.0.1", False, None, "a",  2,    None),
    ("1.0.1b5",            VersionState.CLEAN_PREN,    "1.0.1", False, None, "b",  5,    None),
    ("1.0.1rc1",           VersionState.CLEAN_PREN,    "1.0.1", False, None, "rc", 1,    None),
    ("1.0.1a0.dev0",       VersionState.DEV0_PRE,      "1.0.1", True,  0,    "a",  0,    None),
    ("1.0.1b0.dev0",       VersionState.DEV0_PRE,      "1.0.1", True,  0,    "b",  0,    None),
    ("1.0.1rc0.dev0",      VersionState.DEV0_PRE,      "1.0.1", True,  0,    "rc", 0,    None),
    ("1.0.1a2.dev0",       VersionState.DEV0_PRE,      "1.0.1", True,  0,    "a",  2,    None),
    ("1.0.1a0.dev3",       VersionState.DEVK_PRE,      "1.0.1", True,  3,    "a",  0,    None),
    ("1.0.1b2.dev5",       VersionState.DEVK_PRE,      "1.0.1", True,  5,    "b",  2,    None),
    ("1.0.1rc1.dev1",      VersionState.DEVK_PRE,      "1.0.1", True,  1,    "rc", 1,    None),

    # Post-release
    ("1.0.1.post0",        VersionState.CLEAN_POST0,   "1.0.1", False, None, None, None, 0),
    ("1.0.1.post2",        VersionState.CLEAN_POSTM,   "1.0.1", False, None, None, None, 2),
    ("1.0.1.post5",        VersionState.CLEAN_POSTM,   "1.0.1", False, None, None, None, 5),
    ("1.0.1.post0.dev0",   VersionState.DEV0_POST,     "1.0.1", True,  0,    None, None, 0),
    ("1.0.1.post2.dev0",   VersionState.DEV0_POST,     "1.0.1", True,  0,    None, None, 2),
    ("1.0.1.post0.dev3",   VersionState.DEVK_POST,     "1.0.1", True,  3,    None, None, 0),
    ("1.0.1.post2.dev5",   VersionState.DEVK_POST,     "1.0.1", True,  5,    None, None, 2),
]
# fmt: on


@pytest.mark.parametrize(
    "raw,expected_state,base,is_dev,dev_number,pre_kind,pre_number,post_number",
    _VERSION_MATRIX,
    ids=[f"{raw}={state.name}" for raw, state, *_ in _VERSION_MATRIX],
)
def test_version_parsing(
    raw: str,
    expected_state: VersionState,
    base: str,
    is_dev: bool,
    dev_number: int | None,
    pre_kind: str | None,
    pre_number: int | None,
    post_number: int | None,
) -> None:
    v = Version.parse(raw)
    assert v.raw == raw
    assert v.state == expected_state
    assert v.base == base
    assert v.is_dev == is_dev
    assert v.dev_number == dev_number
    assert v.pre_kind == pre_kind
    assert v.pre_number == pre_number
    assert v.post_number == post_number


_INVALID_VERSIONS = [
    "",
    "not-a-version",
    "abc.def.ghi",
]


@pytest.mark.parametrize("raw", _INVALID_VERSIONS)
def test_version_parse_invalid_raises(raw: str) -> None:
    with pytest.raises((ValueError, Exception)):
        Version.parse(raw)


# ---------------------------------------------------------------------------
# Frozen enforcement: all entity types cannot be mutated
# ---------------------------------------------------------------------------


def _make_version() -> Version:
    return Version.parse("1.0.0")


def _make_package() -> Package:
    return Package(name="pkg", path="packages/pkg", version=_make_version(), deps=[])


def _make_tag() -> Tag:
    return Tag(
        package_name="pkg",
        raw="pkg/v1.0.0",
        version=_make_version(),
        is_baseline=False,
        commit="abc123",
    )


def _make_config() -> Config:
    return Config(
        uvr_version="0.1.0",
        latest_package="",
        python_version="3.12",
        include=frozenset(),
        exclude=frozenset(),
    )


def _make_publishing() -> Publishing:
    return Publishing(
        index="",
        environment="",
        trusted_publishing="automatic",
        include=frozenset(),
        exclude=frozenset(),
    )


def _make_workspace() -> Workspace:
    return Workspace(
        packages={"pkg": _make_package()},
        config=_make_config(),
        runners={},
        publishing=_make_publishing(),
    )


def _make_change() -> Change:
    return Change(
        package=_make_package(),
        baseline=_make_tag(),
        diff_stats="+10 / -5",
        commit_log="abc Fix something",
    )


def _make_release() -> Release:
    return Release(
        package=_make_package(),
        release_version=_make_version(),
        next_version=Version.parse("1.0.1.dev0"),
        release_notes="Fixed a bug.",
        make_latest=False,
    )


def _make_workflow() -> Workflow:
    return Workflow(jobs={})


def _make_plan() -> Plan:
    return Plan(
        workspace=_make_workspace(),
        releases={},
        workflow=_make_workflow(),
        target="local",
    )


_FROZEN_INSTANCES = [
    ("Version", _make_version, "raw", "changed"),
    ("Package", _make_package, "name", "changed"),
    ("Tag", _make_tag, "raw", "changed"),
    ("Config", _make_config, "uvr_version", "changed"),
    ("Publishing", _make_publishing, "index", "changed"),
    ("Workspace", _make_workspace, "publishing", None),
    ("Change", _make_change, "diff_stats", "changed"),
    ("Release", _make_release, "release_notes", "changed"),
    ("Workflow", _make_workflow, "jobs", {}),
    ("Plan", _make_plan, "target", "ci"),
]


@pytest.mark.parametrize(
    "name,factory,field,value",
    _FROZEN_INSTANCES,
    ids=[name for name, *_ in _FROZEN_INSTANCES],
)
def test_frozen_enforcement(name: str, factory: Any, field: str, value: object) -> None:
    obj = factory()
    with pytest.raises((AttributeError, Exception)):
        setattr(obj, field, value)


# ---------------------------------------------------------------------------
# TAG: all fields required, no optional
# ---------------------------------------------------------------------------


def test_tag_requires_all_fields() -> None:
    tag = _make_tag()
    assert tag.raw == "pkg/v1.0.0"
    assert tag.version.raw == "1.0.0"
    assert tag.is_baseline is False
    assert tag.commit == "abc123"


# ---------------------------------------------------------------------------
# BUMP_TYPE: all 9 variants present
# ---------------------------------------------------------------------------


def test_bump_type_has_all_variants() -> None:
    expected = {
        "MAJOR",
        "MINOR",
        "PATCH",
        "ALPHA",
        "BETA",
        "RC",
        "POST",
        "DEV",
        "STABLE",
    }
    actual = {member.name for member in BumpType}
    assert actual == expected


# ---------------------------------------------------------------------------
# MERGE_RESULT
# ---------------------------------------------------------------------------


def test_merge_result() -> None:
    mr = MergeResult(path="release.yml", has_conflicts=True, is_new=False)
    assert mr.has_conflicts is True
    assert mr.is_new is False


# ---------------------------------------------------------------------------
# CHANGE holds reference to PACKAGE, not a copy
# ---------------------------------------------------------------------------


def test_change_holds_package_reference() -> None:
    pkg = _make_package()
    change = Change(
        package=pkg,
        baseline=_make_tag(),
        diff_stats=None,
        commit_log="",
    )
    assert change.package is pkg


# ---------------------------------------------------------------------------
# RELEASE holds reference to PACKAGE
# ---------------------------------------------------------------------------


def test_release_holds_package_reference() -> None:
    pkg = _make_package()
    release = Release(
        package=pkg,
        release_version=_make_version(),
        next_version=Version.parse("1.0.1.dev0"),
        release_notes="",
        make_latest=False,
    )
    assert release.package is pkg


# ---------------------------------------------------------------------------
# JOB and WORKFLOW
# ---------------------------------------------------------------------------


def test_job_construction() -> None:
    job = Job(name="build", needs=["validate"], commands=[])
    assert job.name == "build"
    assert job.needs == ["validate"]
    assert job.commands == []


def test_workflow_jobs_keyed_by_name() -> None:
    j = Job(name="build", needs=[], commands=[])
    wf = Workflow(jobs={"build": j})
    assert "build" in wf.jobs
    assert wf.jobs["build"].name == "build"


# ---------------------------------------------------------------------------
# PLAN holds reference to WORKSPACE
# ---------------------------------------------------------------------------


def test_plan_holds_workspace_reference() -> None:
    ws = _make_workspace()
    plan = Plan(workspace=ws, releases={}, workflow=_make_workflow(), target="local")
    assert plan.workspace is ws


def test_plan_target_values() -> None:
    plan_ci = Plan(
        workspace=_make_workspace(), releases={}, workflow=_make_workflow(), target="ci"
    )
    plan_local = Plan(
        workspace=_make_workspace(),
        releases={},
        workflow=_make_workflow(),
        target="local",
    )
    assert plan_ci.target == "ci"
    assert plan_local.target == "local"


# ---------------------------------------------------------------------------
# PLAN serialization round-trip
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# PLAN_PARAMS defaults
# ---------------------------------------------------------------------------


class TestPlanParamsDefaults:
    def test_bump_type_defaults_to_dev(self) -> None:
        params = PlanParams()
        assert params.bump_type == BumpType.DEV

    def test_pin_defaults_to_true(self) -> None:
        params = PlanParams()
        assert params.pin is True

    def test_commit_defaults_to_true(self) -> None:
        params = PlanParams()
        assert params.commit is True

    def test_push_defaults_to_true(self) -> None:
        params = PlanParams()
        assert params.push is True

    def test_tag_defaults_to_true(self) -> None:
        params = PlanParams()
        assert params.tag is True

    def test_target_defaults_to_local(self) -> None:
        params = PlanParams()
        assert params.target == "local"

    def test_target_accepts_ci(self) -> None:
        params = PlanParams(target="ci")
        assert params.target == "ci"

    def test_bump_type_accepts_all_variants(self) -> None:
        for bt in BumpType:
            params = PlanParams(bump_type=bt)
            assert params.bump_type == bt


# ---------------------------------------------------------------------------
# COMMAND needs_user_confirmation
# ---------------------------------------------------------------------------


class TestCommandConfirmation:
    def test_needs_user_confirmation_defaults_to_false(self) -> None:
        from uv_release.commands import ShellCommand

        cmd = ShellCommand(label="test", args=["true"])
        assert cmd.needs_user_confirmation is False

    def test_needs_user_confirmation_can_be_set(self) -> None:
        from uv_release.commands import ShellCommand

        cmd = ShellCommand(label="test", args=["true"], needs_user_confirmation=True)
        assert cmd.needs_user_confirmation is True

    def test_needs_user_confirmation_survives_json_round_trip(self) -> None:
        from uv_release.commands import ShellCommand

        cmd = ShellCommand(label="test", args=["true"], needs_user_confirmation=True)
        json_str = cmd.model_dump_json()
        restored = ShellCommand.model_validate_json(json_str)
        assert restored.needs_user_confirmation is True


class TestCommandGroup:
    def test_command_group_holds_commands(self) -> None:
        from uv_release.commands import ShellCommand
        from uv_release.types import CommandGroup

        inner = [
            ShellCommand(label="a", args=["true"]),
            ShellCommand(label="b", args=["true"]),
        ]
        group = CommandGroup(
            label="group", commands=inner, needs_user_confirmation=True
        )
        assert len(group.commands) == 2
        assert group.needs_user_confirmation is True

    def test_command_group_type_discriminator(self) -> None:
        from uv_release.types import CommandGroup

        group = CommandGroup(label="group", commands=[])
        assert group.type == "group"

    def test_command_group_execute_stops_on_failure(self) -> None:
        from uv_release.commands import ShellCommand
        from uv_release.types import CommandGroup

        group = CommandGroup(
            label="group",
            commands=[
                ShellCommand(label="fail", args=["false"], check=True),
                ShellCommand(label="never", args=["true"]),
            ],
        )
        assert group.execute() != 0


# ---------------------------------------------------------------------------
# VERSION transformation methods
# ---------------------------------------------------------------------------


class TestVersionTransformations:
    def test_with_pre(self) -> None:
        v = Version.parse("1.0.1")
        result = v.with_pre("a", 2)
        assert result.raw == "1.0.1a2"

    def test_with_post(self) -> None:
        v = Version.parse("1.0.1")
        result = v.with_post(3)
        assert result.raw == "1.0.1.post3"

    def test_bump_major(self) -> None:
        v = Version.parse("1.2.3")
        assert v.bump_major().raw == "2.0.0"

    def test_bump_minor(self) -> None:
        v = Version.parse("1.2.3")
        assert v.bump_minor().raw == "1.3.0"

    def test_bump_patch(self) -> None:
        v = Version.parse("1.2.3")
        assert v.bump_patch().raw == "1.2.4"


# ---------------------------------------------------------------------------
# TAG.ref property
# ---------------------------------------------------------------------------


def test_tag_ref_property() -> None:
    tag = _make_tag()
    assert tag.ref == "refs/tags/pkg/v1.0.0"


# ---------------------------------------------------------------------------
# HOOKS default no-ops
# ---------------------------------------------------------------------------


class TestHooksDefaults:
    def test_pre_plan_returns_params(self) -> None:
        from uv_release.types import Hooks

        h = Hooks()
        params = PlanParams()
        assert h.pre_plan(params) is params

    def test_post_plan_returns_plan(self) -> None:
        from uv_release.types import Hooks

        h = Hooks()
        plan = _make_plan()
        assert h.post_plan(plan) is plan

    def test_build_hooks_are_noop(self) -> None:
        from uv_release.types import Hooks

        h = Hooks()
        plan = _make_plan()
        h.pre_build(plan)
        h.post_build(plan)

    def test_release_hooks_are_noop(self) -> None:
        from uv_release.types import Hooks

        h = Hooks()
        plan = _make_plan()
        h.pre_release(plan)
        h.post_release(plan)

    def test_publish_hooks_are_noop(self) -> None:
        from uv_release.types import Hooks

        h = Hooks()
        plan = _make_plan()
        h.pre_publish(plan)
        h.post_publish(plan)

    def test_bump_hooks_are_noop(self) -> None:
        from uv_release.types import Hooks

        h = Hooks()
        plan = _make_plan()
        h.pre_bump(plan)
        h.post_bump(plan)


# ---------------------------------------------------------------------------
# COMMAND base raises NotImplementedError
# ---------------------------------------------------------------------------


def test_command_base_execute_raises() -> None:
    from uv_release.types import Command

    cmd = Command(label="base")
    with pytest.raises(NotImplementedError):
        cmd.execute()


# ---------------------------------------------------------------------------
# PLAN serialization round-trip
# ---------------------------------------------------------------------------


def test_plan_json_round_trip() -> None:
    """Full Plan survives JSON serialization and deserialization losslessly."""
    from uv_release.commands import (
        BuildCommand,
        CreateReleaseCommand,
        CreateTagCommand,
        SetVersionCommand,
        ShellCommand,
    )

    pkg = _make_package()
    release_version = Version.parse("1.0.0")
    next_version = Version.parse("1.0.1.dev0")

    release = Release(
        package=pkg,
        release_version=release_version,
        next_version=next_version,
        release_notes="Fixed a bug",
        make_latest=True,
    )

    plan = Plan(
        workspace=_make_workspace(),
        releases={"pkg": release},
        workflow=Workflow(
            jobs={
                "uvr-validate": Job(name="uvr-validate"),
                "uvr-build": Job(
                    name="uvr-build",
                    needs=["uvr-validate"],
                    commands=[
                        ShellCommand(label="mkdir", args=["mkdir", "-p", "dist"]),
                        BuildCommand(label="build pkg", package=pkg),
                    ],
                    pre_hook="pre_build",
                    post_hook="post_build",
                ),
                "uvr-release": Job(
                    name="uvr-release",
                    needs=["uvr-build"],
                    commands=[
                        CreateTagCommand(label="tag", tag_name="pkg/v1.0.0"),
                        ShellCommand(label="push tags", args=["git", "push", "--tags"]),
                        CreateReleaseCommand(label="release pkg", release=release),
                    ],
                ),
                "uvr-publish": Job(
                    name="uvr-publish",
                    needs=["uvr-release"],
                ),
                "uvr-bump": Job(
                    name="uvr-bump",
                    needs=["uvr-publish"],
                    commands=[
                        SetVersionCommand(
                            label="bump", package=pkg, version=next_version
                        ),
                    ],
                ),
            },
            job_order=[
                "uvr-validate",
                "uvr-build",
                "uvr-release",
                "uvr-publish",
                "uvr-bump",
            ],
        ),
        target="ci",
    )

    json_str = plan.model_dump_json()
    restored = Plan.model_validate_json(json_str)

    # Top-level fields
    assert restored.target == "ci"
    assert restored.workspace.config.uvr_version == plan.workspace.config.uvr_version
    assert set(restored.workspace.packages.keys()) == {"pkg"}

    # Releases
    assert "pkg" in restored.releases
    r = restored.releases["pkg"]
    assert r.release_version.raw == "1.0.0"
    assert r.next_version.raw == "1.0.1.dev0"
    assert r.release_notes == "Fixed a bug"
    assert r.make_latest is True
    assert r.package.name == "pkg"

    # Workflow structure
    assert set(restored.workflow.jobs.keys()) == {
        "uvr-validate",
        "uvr-build",
        "uvr-release",
        "uvr-publish",
        "uvr-bump",
    }
    assert restored.workflow.job_order == [
        "uvr-validate",
        "uvr-build",
        "uvr-release",
        "uvr-publish",
        "uvr-bump",
    ]

    # Job DAG edges
    assert restored.workflow.jobs["uvr-build"].needs == ["uvr-validate"]
    assert restored.workflow.jobs["uvr-release"].needs == ["uvr-build"]

    # Job hooks
    assert restored.workflow.jobs["uvr-build"].pre_hook == "pre_build"
    assert restored.workflow.jobs["uvr-build"].post_hook == "post_build"

    # Command types survive round-trip
    build_cmds = restored.workflow.jobs["uvr-build"].commands
    assert len(build_cmds) == 2
    assert isinstance(build_cmds[0], ShellCommand)
    assert build_cmds[0].args == ["mkdir", "-p", "dist"]
    assert isinstance(build_cmds[1], BuildCommand)
    assert build_cmds[1].package.name == "pkg"

    release_cmds = restored.workflow.jobs["uvr-release"].commands
    assert len(release_cmds) == 3
    assert isinstance(release_cmds[0], CreateTagCommand)
    assert release_cmds[0].tag_name == "pkg/v1.0.0"
    assert isinstance(release_cmds[1], ShellCommand)
    assert isinstance(release_cmds[2], CreateReleaseCommand)
    assert release_cmds[2].release.package.name == "pkg"

    bump_cmds = restored.workflow.jobs["uvr-bump"].commands
    assert len(bump_cmds) == 1
    assert isinstance(bump_cmds[0], SetVersionCommand)
    assert bump_cmds[0].version.raw == "1.0.1.dev0"
