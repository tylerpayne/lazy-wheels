"""Integration tests for GitRepo using real git repositories."""

from __future__ import annotations

from pathlib import Path

from uv_release.utils.git import GitRepo

from .conftest import add_baseline_tags, modify_file


class TestFindTag:
    def test_existing_tag(self, workspace: Path) -> None:
        add_baseline_tags(workspace)
        repo = GitRepo()
        commit = repo.find_tag("alpha/v1.0.0.dev0-base")
        assert commit is not None
        assert len(commit) == 40

    def test_missing_tag(self, workspace: Path) -> None:
        repo = GitRepo()
        assert repo.find_tag("nonexistent/v1.0.0") is None


class TestListTags:
    def test_matching_prefix(self, workspace: Path) -> None:
        add_baseline_tags(workspace)
        repo = GitRepo()
        tags = repo.list_tags("alpha/v")
        assert "alpha/v1.0.0.dev0-base" in tags

    def test_no_match(self, workspace: Path) -> None:
        add_baseline_tags(workspace)
        repo = GitRepo()
        tags = repo.list_tags("nonexistent/v")
        assert tags == []


class TestPathChanged:
    def test_changed_path(self, workspace: Path) -> None:
        add_baseline_tags(workspace)
        modify_file(workspace, "packages/alpha/new.txt")
        repo = GitRepo()
        head = repo.head_commit()
        baseline = repo.find_tag("alpha/v1.0.0.dev0-base")
        assert baseline is not None
        assert repo.path_changed(baseline, head, "packages/alpha") is True

    def test_unchanged_path(self, workspace: Path) -> None:
        add_baseline_tags(workspace)
        modify_file(workspace, "packages/alpha/new.txt")
        repo = GitRepo()
        head = repo.head_commit()
        baseline = repo.find_tag("beta/v1.0.0.dev0-base")
        assert baseline is not None
        assert repo.path_changed(baseline, head, "packages/beta") is False

    def test_missing_path_returns_true(self, workspace: Path) -> None:
        """Path that doesn't exist in from_commit returns True (new path)."""
        add_baseline_tags(workspace)
        modify_file(workspace, "packages/gamma/new.txt")
        repo = GitRepo()
        head = repo.head_commit()
        baseline = repo.find_tag("alpha/v1.0.0.dev0-base")
        assert baseline is not None
        assert repo.path_changed(baseline, head, "packages/gamma") is True


class TestCommitLog:
    def test_has_commits(self, workspace: Path) -> None:
        add_baseline_tags(workspace)
        modify_file(workspace, "packages/alpha/new.txt")
        repo = GitRepo()
        head = repo.head_commit()
        baseline = repo.find_tag("alpha/v1.0.0.dev0-base")
        assert baseline is not None
        log = repo.commit_log(baseline, head, "packages/alpha")
        assert "modify" in log

    def test_no_commits(self, workspace: Path) -> None:
        add_baseline_tags(workspace)
        repo = GitRepo()
        head = repo.head_commit()
        baseline = repo.find_tag("alpha/v1.0.0.dev0-base")
        assert baseline is not None
        log = repo.commit_log(baseline, head, "packages/alpha")
        assert log == ""


class TestDiffStats:
    def test_has_diff(self, workspace: Path) -> None:
        add_baseline_tags(workspace)
        modify_file(workspace, "packages/alpha/new.txt")
        repo = GitRepo()
        head = repo.head_commit()
        baseline = repo.find_tag("alpha/v1.0.0.dev0-base")
        assert baseline is not None
        stats = repo.diff_stats(baseline, head, "packages/alpha")
        assert stats is not None

    def test_no_diff(self, workspace: Path) -> None:
        add_baseline_tags(workspace)
        repo = GitRepo()
        head = repo.head_commit()
        baseline = repo.find_tag("alpha/v1.0.0.dev0-base")
        assert baseline is not None
        stats = repo.diff_stats(baseline, head, "packages/alpha")
        assert stats is None


class TestCreateTag:
    def test_creates_tag(self, workspace: Path) -> None:
        repo = GitRepo()
        repo.create_tag("test/v1.0.0")
        assert repo.find_tag("test/v1.0.0") is not None


class TestHeadCommit:
    def test_returns_sha(self, workspace: Path) -> None:
        repo = GitRepo()
        sha = repo.head_commit()
        assert len(sha) == 40


class TestIsDirty:
    def test_clean(self, workspace: Path) -> None:
        repo = GitRepo()
        assert repo.is_dirty() is False

    def test_dirty(self, workspace: Path) -> None:
        (workspace / "untracked.txt").write_text("dirty")
        repo = GitRepo()
        assert repo.is_dirty() is True


class TestIsAheadOrBehind:
    def test_no_upstream(self, workspace: Path) -> None:
        """No remote tracking branch returns False."""
        repo = GitRepo()
        assert repo.is_ahead_or_behind() is False


class TestBaselinesIntegration:
    """Test baseline resolution with real tags in a git repo."""

    def test_baseline_tag_with_garbage_tags(self, workspace: Path) -> None:
        """Tags with unparseable versions are skipped during baseline search."""
        from uv_release.states.changes import _find_baseline_tag as find_baseline_tag
        from uv_release.types import Version

        repo = GitRepo()
        # Create a garbage tag and a valid baseline
        repo.create_tag("alpha/vgarbage-not-a-version")
        repo.create_tag("alpha/v1.0.0.dev0-base")

        tag = find_baseline_tag("alpha", Version.parse("1.0.0.dev0"), repo)
        assert tag is not None
        assert tag.raw == "alpha/v1.0.0.dev0-base"

    def test_baseline_skips_base_tags_in_previous_search(self, workspace: Path) -> None:
        """When searching for previous release, baseline tags are skipped."""
        from uv_release.states.changes import _find_baseline_tag as find_baseline_tag
        from uv_release.types import Version

        repo = GitRepo()
        # Only a baseline tag exists, no release tag
        repo.create_tag("alpha/v0.9.0-base")

        # CLEAN_STABLE calls _find_previous_release which should skip -base tags
        tag = find_baseline_tag("alpha", Version.parse("1.0.0"), repo)
        assert tag is None  # no release tag below 1.0.0
