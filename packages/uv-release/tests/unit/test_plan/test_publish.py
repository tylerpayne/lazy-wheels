"""Tests for plan_publish_job: generate publish job for wheel uploads."""

from __future__ import annotations

from uv_release.plan.publish import plan_publish_job
from uv_release.commands import PublishToIndexCommand
from uv_release.types import Job, Package, Publishing, Release, Version


def _version(raw: str) -> Version:
    return Version.parse(raw)


def _package(name: str) -> Package:
    return Package(name=name, path=f"packages/{name}", version=_version("1.0.0.dev0"))


def _release(name: str) -> Release:
    return Release(
        package=_package(name),
        release_version=_version("1.0.0"),
        next_version=_version("1.0.1.dev0"),
    )


class TestPublishFiltering:
    def test_include_filter(self) -> None:
        releases = {"a": _release("a"), "b": _release("b")}
        publishing = Publishing(index="pypi", include=frozenset({"a"}))
        job = plan_publish_job(releases, publishing)
        assert isinstance(job, Job)
        assert len(job.commands) == 1
        assert isinstance(job.commands[0], PublishToIndexCommand)
        assert "a" in job.commands[0].label

    def test_exclude_filter(self) -> None:
        releases = {"a": _release("a"), "b": _release("b")}
        publishing = Publishing(index="pypi", exclude=frozenset({"b"}))
        job = plan_publish_job(releases, publishing)
        assert len(job.commands) == 1
        assert "a" in job.commands[0].label

    def test_no_index_means_no_commands(self) -> None:
        releases = {"a": _release("a")}
        publishing = Publishing()  # no index
        job = plan_publish_job(releases, publishing)
        assert job.commands == []


class TestEmptyPublishable:
    def test_all_excluded(self) -> None:
        releases = {"a": _release("a")}
        publishing = Publishing(index="pypi", exclude=frozenset({"a"}))
        job = plan_publish_job(releases, publishing)
        assert job.commands == []

    def test_empty_releases(self) -> None:
        publishing = Publishing(index="pypi")
        job = plan_publish_job({}, publishing)
        assert job.commands == []

    def test_include_none_matching(self) -> None:
        releases = {"a": _release("a")}
        publishing = Publishing(index="pypi", include=frozenset({"nonexistent"}))
        job = plan_publish_job(releases, publishing)
        assert job.commands == []
