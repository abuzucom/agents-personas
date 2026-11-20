# Changelog

This file documents every notable project change.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
One deviation applies. A version heading parenthesizes the release date.
The format uses `## [1.2.3] (2026-01-01)` instead of a spaced hyphen.
The house style bans that hyphen. `scripts/check_ascii.py` enforces the ban on
this file.
All dates are UTC.
Each date has one entry. Every change still advances the version. A same-day
change renames that day's heading to the new version and merges its items
into the entry. Dates never decrease. Ask the active human when a date is in
doubt.
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.0] (2026-11-20)

### Added
- Add the euler persona under `reviewers/euler/`. It holds `QUALITY.md`,
  `DATA.md`, `PROVENANCE.md`, the deterministic prescan, and all 41 eval
  cases from `abuzucom/euler` at `9488a8c`. The `quality` mode reviews pull
  requests. The `file`, `piece`, and `wholesale` modes run locally.
- Add persona review hooks in `engine/persona_hooks.py`. A persona's
  `review_hooks.py` can add items to each chunk's `REVIEW_TARGET`, check
  each reply, and force a verdict. Head extraction skips blobs over 1 MiB
  and skips the hook for a tree over 64 MiB. The tree listing streams and
  stops past 100,000 entries or 16 MiB. foucault's self-reviews found these
  risks.
- Move the changed and unreviewed path lists from `TRUSTED_CONTEXT` into
  `REVIEW_TARGET`. An author chooses every path. Trusted metadata keeps the
  counts. The active human approved two skeleton edits in the existing
  `tests/test_engine_build_pr_case.py`.
- Run review-stage hooks through `engine/run_hook.py` in a child process
  without `MODEL_API_KEY`. The review process never imports the hook file.
- The review stage rejects a built case when the base, pull request number,
  caps, or persona options differ. The manifest records each one. The euler prescan, the QUALITY.md reply rules, and BLOCK
  on a blocking prescan finding run as euler hooks.
- Add `persona_options` to `review.yml` and `options` to `reviewer.json`.
  The engine rejects an option the manifest does not declare.
- Split each review into a build step and a review step. Persona hooks run
  in the build step. That step holds no provider key.
- Add the `validate_case` eval hook and the case directory to each eval case.
- Add the euler wrapper `.github/workflows/euler-quality-review.yml`.
- Add the euler self-review caller `.github/workflows/euler-quality-review-pr.yml`.
- Pin LF line endings for `reviewers/euler/QUALITY.md`.
- The euler dependency check warns when a JSON manifest is not an object.
  A deep array parses on Python 3.14 where the C stack allows it.
- Allow the synthetic `alice` home path in `tests/test_euler_code_quality.py`
  through `.local-path-allowlist`. The active human approved the entry.
- Record decisions 28 to 31 in `docs/plans/consolidation.md`.
- Add the foucault persona under `reviewers/foucault/`. It holds `AUDIT.md`,
  `DATA.md`, `PROVENANCE.md`, and all 68 eval cases from `abuzucom/foucault`
  at `9ec9681`. The `security` mode reviews pull requests. The `file`,
  `piece`, and `wholesale` modes run locally.
- Add `scripts/check_audit_policy.py` to the foucault persona with its tests.
- Pin LF line endings for `reviewers/foucault/AUDIT.md` in `.gitattributes`.
  The policy checker rejects the CRLF checkout that Windows uses otherwise.
- Add `engine/run_eval.py`. It checks the eval cases of every mode and grades
  live replies through `--model-call`. A persona adds checks in
  `eval/extra_checks.py`. foucault adds its report contract, the exact
  `VERDICT_JSON` keys, and the `omit_provenance` input.
- Add local modes to `reviewer.json`. `local: true` marks a mode without CI
  delivery. `verdict_line` and `verdicts` name its verdict form.
- Add `finding_rules` to `reviewer.json` modes. The shared validator checks
  the finding keys, severities, and class prefix.
- Add the `paths` input to `review.yml`. A pull request without a matching
  changed file gets a skipped check named "No matching files".
- Add `.github/workflows/foucault-security-review.yml`, the foucault wrapper.
  Add `.github/workflows/foucault-security-review-pr.yml`, the self-review
  caller after the Convention Sync Check.
- Add `examples/always-on-caller.yml`, `examples/label-caller.yml`, and
  `docs/migration.md`.
- Record decisions 23 to 27 in `docs/plans/consolidation.md`.
- Add `.github/workflows/review.yml`, the reusable engine workflow.
  - One resolve job validates `personas_ref`, the persona, and the cap
    inputs. It resolves the pull request, `same_repository`, the review
    modes, and the earlier review comments.
  - A fork pull request gets a `skipped` check per mode and no secret.
    `fork_review: true` runs every review in the `fork-review` environment.
  - Each mode runs `engine/run_review.py` and publishes a check run with
    annotations, one fenced comment per head SHA, a step summary, and an
    artifact with `result.json`.
  - No step checks out the pull request head. The token reaches only the
    head fetch step. `MODEL_API_KEY` reaches only the review step.
  - The workflow uses the decision 22 action pins and Python 3.14.
- Add `tests/test_review_workflow.py` for the workflow contract, pins,
  checkout credentials, fork rule, secret scope, and script expressions.

### Changed
- `tests/test_review_workflow.py` lists `persona_options` among the optional
  inputs. The active human approved that existing test edit.
- `tests/test_engine_run_eval.py` adds a `validate_case` test and a case
  directory assertion. The active human approved that existing test edit.
- `tests/test_review_workflow.py` lists `paths` among the optional inputs.
  The active human approved that existing test edit.
- NEEDS-HUMAN warns and never blocks CI. `engine/review_output.py` concludes
  `neutral` for NEEDS-HUMAN whatever `fail_on_block` says. The rendered
  output carries a `warning` line. `review.yml` prints it as a `::warning`
  annotation. `fail_on_block` now gates BLOCK only. The active human
  approved the decision 21 change and the existing test edit.
- Every persona comment uses the euler layout. A hidden marker line opens
  the body. A `## <Persona> <mode> review: <VERDICT>` heading follows, then
  the base and head SHAs, the workflow run link, and one
  `### Chunk <n>: <VERDICT>` section per chunk with the fenced report.
  `engine/review_output.py` builds the whole body and takes `--run-url`.
  `engine/run_review.py` records `base_sha` and `chunk_results`. The active
  human approved the decision 15 change and the existing header test edit.
- Add `engine/run_review.py`. It reviews one mode end to end and writes
  `result.json`. The most severe chunk verdict wins. Unreviewed files forbid
  APPROVE. An invalid reply gets one retry with a validation note. A second
  invalid reply fails the run. An adapter capacity exit records
  NEEDS-HUMAN.
- Add `engine/review_output.py`. It renders the check name, the conclusion,
  the annotations, the comment with its header line, and the run metrics.
  With `fail_on_block` off, BLOCK and NEEDS-HUMAN conclude `neutral`.
- Add the optional `json_mode` key to each `reviewer.json` mode. It names
  the `VERDICT_JSON` mode value the persona prompt emits.
- List the review engine scripts in `hooks/workflow-scripts.txt`. The
  command gate allows `check_reviewers.py`, `render_context.py`, and
  `check_review_response.py`. `build_pr_case.py` routes to consent.
  `call_model.py` and `run_model_command.py` stay unlisted. The active
  human approved the change under Rule 22.
- Remove a controlled-vocabulary phrase from an `engine/reviewers.py`
  comment and a `tests/test_engine_reviewers.py` docstring. The active
  human approved the test docstring change.
- Add `engine/envelope.py`. The JSON review envelope places the title,
  body, file names, and patches inside `REVIEW_TARGET` only. The engine
  caps the title and body and records each truncation. `with_fence_rule`
  appends the untrusted input rule to the persona prompt.
- Add `engine/build_pr_case.py`, ported from `abuzucom/euler` without the
  euler prescan. It reads the diff from git objects and splits it into
  chunks under the mode byte budget. Unreviewable files land in the
  manifest.
- Add optional `max_chunks` and `max_envelope_bytes` caps to each
  `reviewer.json` mode. `resolve_caps` lets a caller lower a cap and clamps
  a higher request.
- Add the shared injection corpus in `engine/eval/injection/`. It covers
  the title, body, path, and patch vectors.
- Add `engine/model_providers.json`, the single provider table.
- Add `engine/call_model.py`, ported from `abuzucom/foucault`. It reports
  token usage per request and writes it to `USAGE_FILE`. `MODEL_PROVIDER`
  selects a table entry by name. A transient status gets one retry.
- Add `engine/run_model_command.py`, ported from `abuzucom/foucault`. It
  runs the caller's adapter script without a shell. The script must stay
  inside the caller workspace. The runner refuses backslashes and drive
  prefixes in the command.
- Add `engine/check_review_response.py`, ported from `abuzucom/foucault`.
  It enforces the shared verdict contract, the expected mode, and a file
  and line for each finding.
- Add the persona manifest schema in `engine/reviewers.py`. A manifest
  declares modes with review delivery, context delivery, or both. Exactly
  one mode is the default.
- Add `engine/check_reviewers.py`. It validates every
  `reviewers/<name>/reviewer.json` and the template.
- Add `engine/render_context.py`. It prints one context-delivery mode for
  an agent prompt. The output equals the prompt bytes on every platform.
- Add the `reviewers/_template/` scaffold for a new persona.
- Record decisions 16, 21, and 22 in `docs/plans/consolidation.md`. The
  engine accepts `APPROVE`, `BLOCK`, and `NEEDS-HUMAN`. A non-gating
  verdict sets the mode check to `neutral`. Engine workflows use the euler
  and generay action pins.

### Fixed
- Ignore `.comment-drafts/`. The directory holds comment and pull request
  body drafts for `scripts/trusted_gh.py` and never belongs in commits.
- Disable automatic Git maintenance in the digest index test fixture. The
  fixture copy failed when detached maintenance removed its lock file.

### Added
- Add `docs/plans/consolidation.md`. The plan moves the five PR checker
  repositories into this repository.
- Adopt the agents policy from `abuzucom/agents` at
  `909b93702273befaec9227ee892fe1a2261a4a41`.
- Add `AGENTS.md` and its synchronized client copies.
- Add the complete gate set for claude, codex, gemini, and antigravity.
  The set covers hooks, client registrations, shared modules, checkers,
  tests, and `shared-files.json`.
- Add the local-path checker with an approved `.local-path-allowlist`.
- Add the `sync-check`, `agents-compliance`, `agents-md-compliance`, and
  `gate-integrity` workflows.
- Add `requirements-checkers.txt` with hash-pinned PyYAML 6.0.3.
- Add `docs/project-orientation.md` and `docs/template-drift.md`.
