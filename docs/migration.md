# Migrate callers to agents-personas

Each persona moves from its own repository to one wrapper workflow here. The
wrappers share `.github/workflows/review.yml`. Callers change the `uses:`
line and the inputs below. Secret names stay unchanged.

Pin `uses:` and `personas_ref` to the same full commit SHA of
`abuzucom/agents-personas`. A tag or branch name fails validation.

## Caller patterns

Two caller files cover the planned workflow:

- `examples/always-on-caller.yml` runs foucault and euler on every pull
  request after CI. Mark `foucault / security` and `euler / quality` as
  required checks.
- `examples/label-caller.yml` runs adorno, generay, and havel when a
  maintainer adds a label. These checks stay optional.

| Label | Job | Mode |
|---|---|---|
| `review:adorno` | adorno | default |
| `review:generay` | generay | default (`time`) |
| `review:generay-sync` | generay-sync | `sync` |
| `review:havel` | havel | default |

A person adds every label. A new push to a labeled pull request reviews
again.

The `paths` input limits a review to pull requests that touch matching files.
It takes newline-separated globs. `**` crosses directories and `*` stays in
one. A pull request without a matching file gets a skipped check named
`<persona> / <mode>` with the title "No matching files".

```yaml
    with:
      personas_ref: "<sha>"
      paths: |
        src/**
        api/**
```

### Required-check caveat

A `workflow_run` caller posts its check on the pull request head SHA after CI
finishes. Branch protection waits for a required check that never arrives:

- A CI run that GitHub skips, for example through a `paths-ignore` filter,
  starts no `workflow_run` event. The review check never appears.
- A `paths` input that matches no changed file posts a `skipped` check.
  GitHub treats a skipped required check as passed.
- A fork pull request without `fork_review: true` posts a `skipped` check.

Give the CI workflow no path filter when branch protection requires a review
check. Keep each check from the label caller optional. A required check from
that caller stops each pull request without the label from merging.

## foucault

foucault moves from `abuzucom/foucault` to the `foucault` persona.

| Old | New |
|---|---|
| `abuzucom/foucault/.github/workflows/security-review.yml@<sha>` | `abuzucom/agents-personas/.github/workflows/foucault-security-review.yml@<sha>` |
| `audit_ref` | `personas_ref` |
| `model_call_command` (required) | `model_call_command` (optional, empty uses the engine adapter) |
| `pr_comment` | `pr_comment` |
| `fail_on_block` gates BLOCK and NEEDS-HUMAN | `fail_on_block` gates BLOCK. NEEDS-HUMAN warns and concludes neutral |
| `fork_review` | `fork_review` |
| `pr_number`, `base_sha`, `head_sha`, `head_repo_url`, `head_repo_full_name` | the same names |
| none | `modes`, empty selects `security` |
| none | `paths` |

The secret stays `MODEL_API_KEY` with `required: false`. Map it from the
provider secret, for example `OLLAMA_API_KEY`. The `fork-review` environment
name stays unchanged.

The check run name is `foucault / security`. The comment uses the shared
layout with a `## Foucault security review: <VERDICT>` heading.

foucault's File, Piece, and Wholesale modes run locally as the `file`,
`piece`, and `wholesale` modes. `reviewers/foucault/eval/README.md` shows the
commands. `python reviewers/foucault/scripts/check_audit_policy.py` replaces
`make audit-check` for the prompt checks.
