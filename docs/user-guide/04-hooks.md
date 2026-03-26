# Add CI Hooks

The release pipeline has four hook points. Edit `.github/workflows/release.yml` directly to customize them.

| Hook | When it runs | Common use |
|------|-------------|------------|
| `pre-build` | Before build | Tests, linting |
| `post-build` | After build | Integration tests |
| `pre-release` | Before publish | Approval gates |
| `post-release` | After finalize | PyPI publish, notifications |

Unconfigured hooks have a no-op default step and are auto-skipped in the release plan.

## Example: gate releases on tests

```yaml
  pre-build:
    runs-on: ubuntu-latest
    if: ${{ !contains(fromJSON(inputs.plan).skip, 'pre-build') }}
    steps:
    - uses: actions/checkout@v4
      with:
        fetch-depth: 0
    - uses: astral-sh/setup-uv@v5
      with:
        python-version: ${{ fromJSON(inputs.plan).python_version }}
    - name: Lint, typecheck, and test
      run: |
        uv sync --all-packages
        uv run poe check
        uv run poe test
```

## Example: Slack notification after release

```yaml
  post-release:
    runs-on: ubuntu-latest
    if: ${{ always() && !failure() && !contains(fromJSON(inputs.plan).skip, 'post-release') }}
    needs:
    - finalize
    steps:
    - name: Notify Slack
      env:
        UVR_PLAN: ${{ inputs.plan }}
      run: |
        CHANGED=$(echo "$UVR_PLAN" | jq -r '.changed | keys | join(", ")')
        curl -X POST "$SLACK_WEBHOOK" -d "{\"text\": \"Released: $CHANGED\"}"
```

## Accessing the plan in hooks

The full release plan JSON is available as `${{ inputs.plan }}`. Use `fromJSON(inputs.plan)` in expressions:

```yaml
    if: fromJSON(inputs.plan).changed['my-package'] != null
    env:
      VERSION: ${{ fromJSON(inputs.plan).changed['my-package'].version }}
```

## Validate after editing

```bash
uvr validate
```

Errors for invalid structure, warnings for modified core job fields.
---

**Under the hood:** [Workflow model internals](../under-the-hood/05-workflow-model.md)
