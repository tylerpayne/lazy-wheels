# Publish to PyPI

The release workflow creates GitHub releases with wheels attached. To also publish to PyPI, edit the `post-release` job to download the wheel and publish it using [trusted publishing](https://docs.pypi.org/trusted-publishers/).

## 1. Add permissions

Add `id-token: write` to the top-level permissions in `release.yml`:

```yaml
permissions:
  contents: write
  id-token: write
```

## 2. Edit the post-release job

Replace the no-op step with download + publish steps:

```yaml
  post-release:
    runs-on: ubuntu-latest
    if: ${{ always() && !failed() && !cancelled() && !contains(fromJSON(inputs.plan).skip, 'post-release') }}
    needs:
    - uvr-finalize
    environment: pypi
    steps:
    - name: Download wheel for PyPI
      if: fromJSON(inputs.plan).changed['my-package'] != null
      env:
        GH_TOKEN: ${{ github.token }}
        VERSION: ${{ fromJSON(inputs.plan).changed['my-package'].version }}
      run: |
        mkdir -p dist
        gh release download "my-package/v${VERSION}" --repo "${{ github.repository }}" --pattern "my_package-*.whl" --dir dist
    - uses: pypa/gh-action-pypi-publish@release/v1
      if: fromJSON(inputs.plan).changed['my-package'] != null
```

Replace `my-package` with your package name and `my_package` with the distribution name (underscores).

## 3. Configure trusted publishing on PyPI

On [pypi.org](https://pypi.org), go to your package's settings and add a trusted publisher:

- **Repository**: `your-org/your-repo`
- **Workflow**: `release.yml`
- **Environment**: `pypi`

## 4. Create the GitHub environment

In your repo's Settings > Environments, create an environment called `pypi`.

## 5. Validate and commit

```bash
uvr validate
git add .github/workflows/release.yml
git commit -m "Add PyPI trusted publishing"
git push
```

## Re-running PyPI publish

If the post-release job failed (e.g., trusted publisher not configured), fix the issue and re-dispatch:

```bash
uvr release --skip-to post-release --reuse-release -y
```

Or dispatch manually via the GitHub Actions UI with the original plan JSON and `skip` set to all jobs except `post-release`.
---

**Under the hood:** [CI execution internals](../under-the-hood/07-ci-execution.md)
