# Post-releases

Post-releases publish a corrected version of an already-released package without bumping the version number. They follow [PEP 440](https://peps.python.org/pep-0440/#post-releases) versioning.

## Usage

Use `uvr bump` to enter the post-release cycle, then `uvr release` to publish:

```bash
uvr bump --all --post        # advance post number → 1.2.3.post1.dev0
uvr release                  # publishes 1.2.3.post1
```

## How it works

1. `uvr bump --post` increments the post-release number (e.g., `.post0` → `.post1`)
2. `uvr release` strips `.devN` and publishes `X.Y.Z.postN`
3. After release, the pyproject.toml version is bumped to `X.Y.Z.post(N+1).dev0`

## Version ordering

Post-releases sort after the stable release but before the next version:

```
1.0.1 < 1.0.1.post0 < 1.0.1.post1 < 1.0.2.dev0 < 1.0.2
```

## When to use

- **Hotfix for a released version**: a critical bug needs to be patched on an older release while main has moved on. Check out the release tag, fix, and publish as a post-release.
- **Packaging fix**: the wheel was built incorrectly but the source code is fine
- **Metadata correction**: wrong description, classifiers, or dependency constraints
- **Documentation-only change**: README or other bundled docs needed updating

## Tag conflict resolution

If `uvr release` detects that a release tag already exists (e.g., you already published `1.2.3`), it will suggest a post-release or version bump:

```
These tags/releases already exist and would conflict:
  my-pkg/v1.2.3

To resolve, either:
  1. Use uvr bump --post to publish a post-release
  2. Bump past the conflict:
     uvr bump --package my-pkg --patch
```

## Workflow

Post-releases are made from the original release tag, not from main. **Take care merging post-release branches back to main** — pyproject.toml versions will conflict since the branch is based on an old tag.

```bash
# 1. Check out the original release tag
git checkout my-pkg/v1.2.3

# 2. Create a post-release branch
git checkout -b post-release/my-pkg/v1.2.3

# 3. Make the fix (code, packaging, metadata, etc.)
# ...

# 4. Commit and push
git add -A
git commit -m "fix: correct widget parsing in my-pkg"
git push -u origin post-release/my-pkg/v1.2.3

# 5. Enter post-release cycle and publish
uvr bump --all --post
uvr release
```

## Merging

**TAKE CARE** merging post-release branches back to main. The branch is based on an old tag, so pyproject.toml versions will conflict — the branch has `X.Y.Z.post1.dev0` while main has `X.Y.Z+1.dev0`.

Two options for getting the fix onto main:

**Option 1: Cherry-pick** (simpler when the fix is small)

```bash
git checkout main
git cherry-pick <fix-commit-hash>    # pick the fix, not the finalize commits
git push
```

**Option 2: Merge and resolve conflicts** (better when the fix touches many files)

```bash
git checkout main
git merge --no-ff post-release/my-pkg/v1.2.3
# resolve conflicts: accept main's versions in pyproject.toml and uv.lock
git push
```

Leave the post-release branch as-is after publishing. It serves as a record of the hotfix.

## Tag format

```
my-pkg/v1.2.3.post0
my-pkg/v1.2.3.post1
```
