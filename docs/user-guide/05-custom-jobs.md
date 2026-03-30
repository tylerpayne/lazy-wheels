# Custom Workflow Jobs

The generated `release.yml` has four core jobs. You can add your own jobs by editing the YAML directly — wire them into the pipeline via `needs`.

## Add tests before build

```yaml
checks:
  runs-on: ubuntu-latest
  if: ${{ !contains(fromJSON(inputs.plan).skip, 'checks') }}
  steps:
    - uses: actions/checkout@v4
    - uses: astral-sh/setup-uv@v6
    - run: uv sync --all-packages
    - run: uv run poe check
    - run: uv run poe test

uvr-build:
  needs: [checks]         # build waits for checks to pass
  # ... (rest of build job unchanged)
```

## Publish to PyPI after release

```yaml
pypi-publish:
  runs-on: ubuntu-latest
  needs: [uvr-bump]
  if: ${{ always() && !failure() && !cancelled() && !contains(fromJSON(inputs.plan).skip, 'pypi-publish') && fromJSON(inputs.plan).changed['my-package'] != null }}
  environment: pypi
  steps:
    - name: Download wheel
      env:
        GH_TOKEN: ${{ github.token }}
        VERSION: ${{ fromJSON(inputs.plan).changed['my-package'].release_version }}
      run: |
        mkdir -p dist
        gh release download "my-package/v${VERSION}" --repo "${{ github.repository }}" --pattern "my_package-*.whl" --dir dist
    - uses: pypa/gh-action-pypi-publish@release/v1
```

Requires:
1. `id-token: write` in the top-level `permissions`
2. A [trusted publisher](https://docs.pypi.org/trusted-publishers/) configured on PyPI
3. A `pypi` environment in your repo's Settings > Environments

## Send Slack notifications

```yaml
notify:
  runs-on: ubuntu-latest
  needs: [uvr-bump]
  if: ${{ always() && !failure() && !cancelled() && !contains(fromJSON(inputs.plan).skip, 'notify') }}
  steps:
    - name: Notify Slack
      env:
        UVR_PLAN: ${{ inputs.plan }}
      run: |
        CHANGED=$(echo "$UVR_PLAN" | jq -r '.changed | keys | join(", ")')
        curl -X POST "$SLACK_WEBHOOK" -d "{\"text\": \"Released: $CHANGED\"}"
```

## Access the plan in custom jobs

The full release plan JSON is available as `${{ inputs.plan }}`. Use `fromJSON(inputs.plan)` in expressions:

```yaml
if: fromJSON(inputs.plan).changed['my-package'] != null
env:
  VERSION: ${{ fromJSON(inputs.plan).changed['my-package'].release_version }}
```

## Tips

- **Use the skip mechanism.** Add `if: ${{ !contains(fromJSON(inputs.plan).skip, '<job-name>') }}` so the job can be skipped with `uvr release --skip <job-name>`.
- **Gate core jobs via `needs`.** Add your job to a core job's `needs` list to block it.
- **Validate after editing:** `uvr workflow validate`
- **Use `always() && !failure() && !cancelled()`** for jobs that follow skippable upstream jobs.
---

**Under the hood:** [CI execution internals](../under-the-hood/07-ci-execution.md)
