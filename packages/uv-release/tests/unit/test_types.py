"""Tests for frozen entity types and VERSION parsing."""

from __future__ import annotations

from typing import Any

import pytest

from uv_release.types import (
    BumpType,
    Change,
    Config,
    GitState,
    Job,
    MergeResult,
    Package,
    Plan,
    Publishing,
    Release,
    Tag,
    Version,
    VersionState,
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
    return Package(
        name="pkg", path="packages/pkg", version=_make_version(), dependencies=[]
    )


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


def _make_plan() -> Plan:
    return Plan()


_FROZEN_INSTANCES = [
    ("Version", _make_version, "raw", "changed"),
    ("Package", _make_package, "name", "changed"),
    ("Tag", _make_tag, "raw", "changed"),
    ("Config", _make_config, "uvr_version", "changed"),
    ("Publishing", _make_publishing, "index", "changed"),
    ("Workspace", _make_workspace, "publishing", None),
    ("Change", _make_change, "diff_stats", "changed"),
    ("Release", _make_release, "release_notes", "changed"),
    ("Plan", _make_plan, "python_version", "3.11"),
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
# JOB
# ---------------------------------------------------------------------------


def test_job_construction() -> None:
    job = Job(name="build", commands=[])
    assert job.name == "build"
    assert job.commands == []


# ---------------------------------------------------------------------------
# GIT STATE
# ---------------------------------------------------------------------------


class TestGitState:
    def test_defaults(self) -> None:
        gs = GitState()
        assert gs.is_dirty is False
        assert gs.is_ahead_or_behind is False

    def test_dirty(self) -> None:
        gs = GitState(is_dirty=True)
        assert gs.is_dirty is True
        assert gs.is_ahead_or_behind is False

    def test_ahead_or_behind(self) -> None:
        gs = GitState(is_ahead_or_behind=True)
        assert gs.is_dirty is False
        assert gs.is_ahead_or_behind is True

    def test_frozen(self) -> None:
        gs = GitState()
        with pytest.raises((AttributeError, Exception)):
            setattr(gs, "is_dirty", True)


# ---------------------------------------------------------------------------
# PLAN defaults
# ---------------------------------------------------------------------------


def test_plan_defaults() -> None:
    plan = Plan()
    assert plan.build_matrix == [["ubuntu-latest"]]
    assert plan.python_version == "3.12"
    assert plan.publish_environment == ""
    assert plan.skip == []
    assert plan.jobs == []


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
    def test_pre_plan_returns_action(self) -> None:
        from uv_release.types import Hooks

        h = Hooks()
        assert h.pre_plan(None, "action") == "action"

    def test_post_plan_returns_plan(self) -> None:
        from uv_release.types import Hooks

        h = Hooks()
        plan = _make_plan()
        assert h.post_plan(None, None, plan) is plan

    def test_build_hooks_are_noop(self) -> None:
        from uv_release.types import Hooks

        h = Hooks()
        h.pre_build()
        h.post_build()

    def test_release_hooks_are_noop(self) -> None:
        from uv_release.types import Hooks

        h = Hooks()
        h.pre_release()
        h.post_release()

    def test_publish_hooks_are_noop(self) -> None:
        from uv_release.types import Hooks

        h = Hooks()
        h.pre_publish()
        h.post_publish()

    def test_bump_hooks_are_noop(self) -> None:
        from uv_release.types import Hooks

        h = Hooks()
        h.pre_bump()
        h.post_bump()


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
        build_matrix=[["ubuntu-latest"]],
        python_version="3.12",
        publish_environment="pypi",
        skip=["build"],
        jobs=[
            Job(name="validate"),
            Job(
                name="build",
                commands=[
                    ShellCommand(label="mkdir", args=["mkdir", "-p", "dist"]),
                    BuildCommand(label="build pkg", package=pkg),
                ],
                pre_hook="pre_build",
                post_hook="post_build",
            ),
            Job(
                name="release",
                commands=[
                    CreateTagCommand(label="tag", tag_name="pkg/v1.0.0"),
                    ShellCommand(label="push tags", args=["git", "push", "--tags"]),
                    CreateReleaseCommand(label="release pkg", release=release),
                ],
            ),
            Job(name="publish"),
            Job(
                name="bump",
                commands=[
                    SetVersionCommand(label="bump", package=pkg, version=next_version),
                ],
            ),
        ],
    )

    json_str = plan.model_dump_json()
    restored = Plan.model_validate_json(json_str)

    # Top-level fields
    assert restored.build_matrix == [["ubuntu-latest"]]
    assert restored.python_version == "3.12"
    assert restored.publish_environment == "pypi"
    assert restored.skip == ["build"]

    # Jobs structure
    assert len(restored.jobs) == 5
    assert [j.name for j in restored.jobs] == [
        "validate",
        "build",
        "release",
        "publish",
        "bump",
    ]

    # Job hooks
    build_job = restored.jobs[1]
    assert build_job.pre_hook == "pre_build"
    assert build_job.post_hook == "post_build"

    # Command types survive round-trip
    build_cmds = build_job.commands
    assert len(build_cmds) == 2
    assert isinstance(build_cmds[0], ShellCommand)
    assert build_cmds[0].args == ["mkdir", "-p", "dist"]
    assert isinstance(build_cmds[1], BuildCommand)
    assert build_cmds[1].package.name == "pkg"

    release_cmds = restored.jobs[2].commands
    assert len(release_cmds) == 3
    assert isinstance(release_cmds[0], CreateTagCommand)
    assert release_cmds[0].tag_name == "pkg/v1.0.0"
    assert isinstance(release_cmds[1], ShellCommand)
    assert isinstance(release_cmds[2], CreateReleaseCommand)
    assert release_cmds[2].release.package.name == "pkg"

    bump_cmds = restored.jobs[4].commands
    assert len(bump_cmds) == 1
    assert isinstance(bump_cmds[0], SetVersionCommand)
    assert bump_cmds[0].version.raw == "1.0.1.dev0"
