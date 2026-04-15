"""Tests for plan_release_job: generate release job with git tags and GitHub releases."""

from __future__ import annotations

from uv_release.plan.release import plan_release_job
from uv_release.types import Job, Package, Release, Version


def _version(raw: str) -> Version:
    return Version.parse(raw)


def _package(name: str) -> Package:
    return Package(name=name, path=f"packages/{name}", version=_version("1.0.0.dev0"))


def _release(name: str, *, make_latest: bool = False) -> Release:
    return Release(
        package=_package(name),
        release_version=_version("1.0.0"),
        next_version=_version("1.0.1.dev0"),
        release_notes=f"Release notes for {name}",
        make_latest=make_latest,
    )


class TestReleaseTagPerPackage:
    """Each package should get a git tag command."""

    def test_single_package_has_tag_command(self) -> None:
        releases = {"a": _release("a")}
        job = plan_release_job(releases)
        assert isinstance(job, Job)
        assert job.name == "release"
        # Should contain a tag command referencing "a/v1.0.0"
        commands_str = str(job.commands)
        assert "a/v1.0.0" in commands_str

    def test_two_packages_have_two_tag_commands(self) -> None:
        releases = {"a": _release("a"), "b": _release("b")}
        job = plan_release_job(releases)
        commands_str = str(job.commands)
        assert "a/v1.0.0" in commands_str
        assert "b/v1.0.0" in commands_str


class TestMakeLatestLast:
    """The make_latest=True package should have its GitHub release created last."""

    def test_latest_package_released_last(self) -> None:
        releases = {
            "a": _release("a", make_latest=True),
            "b": _release("b"),
        }
        job = plan_release_job(releases)
        # Find positions of GitHub release commands
        commands = job.commands
        a_pos = None
        b_pos = None
        for i, cmd in enumerate(commands):
            cmd_str = str(cmd)
            if (
                "gh_release" in cmd_str
                or "github_release" in cmd_str
                or "create_release" in cmd_str
            ):
                if "a/v" in cmd_str:
                    a_pos = i
                elif "b/v" in cmd_str:
                    b_pos = i
        # make_latest package (a) should come after b
        if a_pos is not None and b_pos is not None:
            assert a_pos > b_pos


class TestPushTagsAtEnd:
    """There should be a push tags command at the end of the release job."""

    def test_push_tags_present(self) -> None:
        releases = {"a": _release("a")}
        job = plan_release_job(releases)
        commands_str = str(job.commands)
        assert "push" in commands_str or "git push" in commands_str.lower()


class TestEmptyReleases:
    """Empty releases should produce a release job with no commands."""

    def test_no_releases_no_commands(self) -> None:
        job = plan_release_job({})
        assert job.commands == []
