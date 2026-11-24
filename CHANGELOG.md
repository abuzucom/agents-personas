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

## [0.19.3] (2026-11-24)

### Added
- Add `archive/` with the five source persona repositories. It holds Git
  bundles of every branch and tag for foucault, euler, and adorno. It holds
  a `main` tree zip and a JSON export of pull requests, reviews, comments,
  issues, and releases for all five. The generay and havel zips omit eight
  Terraform and Kubernetes eval cases. `archive/README.md` lists each case
  and the restore steps. `archive/SHA256SUMS` lists each file digest.
- Add `reviewers/<name>/README.md` for each persona. Each README adapts the
  source repository README to the engine. It keeps the design position,
  the policy summary, the modes, the coverage, and the customization notes.
  It points the old install and CI sections at the wrapper.
- Expand the root README with the review flow, adoption steps, local use,
  the repository layout, and the verification commands. It links each
  persona README.
- Add `.github/workflows/havel-privacy-review.yml`. It forwards the engine
  inputs and an optional `regimes` input. toJSON escapes the value into
  `persona_options`. `MODEL_API_KEY` stays optional. `docs/migration.md`
  maps the old `privacy-review.yml` inputs.
- Add `.github/workflows/havel-privacy-review-pr.yml`. This repository
  reviews with havel only under the `havel-scan-requested` label, with the
  `baseline` scope. The concurrency group sits on the job.
- Show the `regimes` input in `examples/label-caller.yml`. Extend the
  yamllint paths and the README table to the havel workflows.
- Add the havel persona under `reviewers/havel`. It comes from
  `abuzucom/havel` at `5857143`. `PROVENANCE.md` maps every file. The
  `privacy` mode reviews pull requests with `bundles/all-full.md`. The source
  workflow sent `AUDIT.md` alone, without the scope profiles, class check
  files, regime deltas, or scope boundary the hub points at. The `file`, `piece`, `wholesale`, and
  `data-map` modes run locally. 102 of the 104 source eval cases moved. The
  two cases with Terraform fixtures stay in the source repository, because
  the gates protect Terraform source.
- Declare the trusted `regimes` option. The caller value reaches the model in
  `TRUSTED_CONTEXT.options.regimes`. The `baseline` and `undeclared` values
  carry fixed notes in the check summary and the comment.
- Add `reviewers/havel/review_hooks.py`. A review reply must carry the
  `NOT LEGAL ADVICE:` line directly above its final verdict line.
- Extend `make lint-code` to the havel persona and its tests.

### Changed
- Type the BLOCK confirmation run records. `run_review.RunRecord` names the
  label, verdict, and report fields. `ChunkResult.runs` holds those records.
  `result.json` keeps its shape.
- Fit the havel `AUDIT.md` to the engine in two places. Step 0b names
  `TRUSTED_CONTEXT.options.regimes` as the workflow input and ranks it above
  the bundle header scope line. Section 6 moves the `NOT LEGAL ADVICE:` line
  above the verdict line, because the engine requires `VERDICT_JSON` last.

### Fixed
- Start a self-review after the Convention Sync Check only when that run
  succeeds. Each of the five callers checks the `workflow_run`
  conclusion. A failed or cancelled sync run calls no model. Label events
  still start a review at once.
- Name the pull request in each caller lock. Two pull requests on one head
  commit no longer cancel each other. A fork `workflow_run` payload lists
  no pull request. The head branch then stands in for the number.
- Lint the adorno wrapper and caller with yamllint, as the other persona
  workflows. `tests/test_persona_caller_gates.py` requires every persona
  workflow in the yamllint paths.
- Pin down padded havel `regimes` values in
  `tests/test_havel_scope_padding.py`. Each one passes the hook and carries
  the note of its trimmed value.
- Tell maintainers what a havel run without regime deltas left unchecked.
  The `baseline`, `undeclared`, and empty `regimes` notes now state that
  regime-specific issues may exist that the run did not check. The empty
  default carried no note before. `AUDIT.md` step 0b has the report name
  the unchecked regime-specific obligations on its `Unseen:` line under
  those scopes. The bundles carry the rule after the rebuild.
- Check the havel `regimes` option before a review. The `case_context`
  hook refuses a name outside `docs/regimes/scope-profiles.md` and a blank
  list entry. The build then stops before any envelope exists. The empty
  value still declares no scope. The active human approved the two
  assertion updates in the existing `tests/test_havel_persona.py`.

## [0.17.2] (2026-11-23)

### Added
- Add the adorno persona under `reviewers/adorno`. It comes from
  `abuzucom/adorno` at `97a2c84`. `PROVENANCE.md` maps every file. Every
  mode loads the prebuilt `bundles/ui-full.md`. A test rebuilds the bundle
  and requires a byte-for-byte match. The `ui` mode reviews pull requests.
  The `file`, `piece`, `wholesale`, and `design-spec` modes run locally.
  The bundle builder refuses a `bundles/` directory that is a symlink or
  resolves outside the persona root. No write then leaves the root.
- Add `.github/workflows/adorno-ui-review.yml` with an optional
  `MODEL_API_KEY`. `docs/migration.md` maps the old `ui-review.yml` inputs.
- Add `.github/workflows/adorno-ui-review-pr.yml`. This repository reviews
  with adorno only under the `adorno-scan-requested` label.
- Extend `make lint-code` to the adorno persona and its tests.

### Changed
- Show each run of a BLOCK confirmation under its own comment heading.
  `Run 1` and `Run 2 (confirmation)` each carry the run verdict and a
  separate fenced report. One fence with two verdict lines read as a
  single contradictory review. A `chunk_results` entry with a reported
  confirmation gains a `runs` list of label, verdict, and report in
  `result.json`. The combined `report` string keeps its form. Every other
  chunk entry and comment keeps its shape.

### Fixed
- Run persona scans requested together side by side. Every label event
  reached every self-review caller. A caller skipped its job for another
  persona label, but its workflow-level concurrency group still cancelled
  the running review of its own persona. Each caller now holds the group
  on its review job. A skipped job joins no group. The active human
  approved the lookup update in the existing
  `tests/test_scan_request_label.py`.
- Stop reporting a replaced review as a failure. A cancelled review
  posted `Review failed before a verdict`. It now publishes no check run.
  The newer run that replaced it owns the check. A stale check therefore
  never lands after the newer verdict. The gate step skips a cancelled
  job.

## [0.16.0] (2026-11-22)

### Added
- Accept `"trusted": true` on a `reviewer.json` option. The engine places
  each trusted value in `TRUSTED_CONTEXT.options`, under the trusted
  digest. Untrusted options stay out of the envelope. An envelope without
  trusted options keeps its old shape.
- Accept a top-level `option_notes` block in `reviewer.json`. It maps a
  trusted string option value to one fixed note. The engine adds the note
  to the result, the check summary, and the pull request comment.
- List the persona eval runner and the persona checkers in
  `hooks/workflow-scripts.txt`. A structure eval and every persona checker
  run without a prompt. A model eval routes to consent and accepts only the
  engine adapter `engine.call_model:call_model`. The active human approved
  the protected edit under Rule 22.
- Add `make lint-code` and the `Code Lint` workflow. ruff, mypy, and
  yamllint check the engine, the personas, the matching tests, and the
  workflows this repository owns. `requirements-dev.txt` pins ruff 0.17.4, mypy
  2.4.1, and yamllint 1.38.0 by hash. The ruff and yamllint configs come
  from `abuzucom/euler`.

### Changed
- Send provider calls through `http.client`. Any scheme but HTTPS fails
  before a connection opens. HTTPS_PROXY, NO_PROXY, and proxy credentials
  keep the urllib behavior. The active human approved moving the two
  `urlopen` patches in the existing `tests/test_engine_call_model.py`.
- Each engine script adds its own directory to the import path in place
  of the fallback import pair.
- Apply ruff format to the engine, the personas, and the matching tests.
  The active human approved formatting the existing test files. The active
  human also approved five mechanical lint edits in those files.
- Wrap the long lines of the workflows this repository owns. Every
  workflow parses to the same values.

### Fixed
- Require every euler finding to cite a file and line inside the review
  target, as generay does. A pull request line falls inside a hunk of the
  file patch. A local line falls inside the file. The line must be a
  positive integer. The active human approved the expected-value update in
  the existing `tests/test_euler_quality_reply.py`.
- A forced_verdict hook result without two fields raises ReviewError. A
  persona hook file without a module loader raises ValueError.

## [0.14.1] (2026-11-21)

### Added
- Add the generay persona under `reviewers/generay`. It comes from
  `abuzucom/generay` at `309d425`. `PROVENANCE.md` maps every file.
  The `time` mode reviews pull requests. The `sync` mode delivers context
  only. The `file`, `piece`, `wholesale`, and `contract` modes run
  locally. The time prescan places advisory candidates in the review
  target. The reply hook applies the generay reply rules.
- Add `.github/workflows/generay-time-review.yml`. The wrapper requires
  `MODEL_API_KEY` and adds `fork_review`. `docs/migration.md` maps the
  old `time-review.yml` inputs.
- Add `.github/workflows/generay-time-review-pr.yml`. This repository
  reviews with generay only under the `generay-scan-requested` label.
- Accept a list of up to four prompt files per mode. The engine joins the
  files in order.
- Add `json_mode` and `require_coverage` to the template review mode.
- Add the `stop-requested` label. It pauses every persona review on a pull
  request, scan requests included. A paused review publishes a skipped
  check titled "Scans stopped".
- Add `.github/workflows/stop-requested-notice.yml`. It posts a comment
  when a person adds `stop-requested`. The comment says to remove the label
  to review before merge.
- Review the current head when a person removes `stop-requested`. The
  self-review callers and `examples/label-caller.yml` listen to
  `unlabeled`. The active human approved the new trigger types in the
  existing `tests/test_scan_request_label.py` and
  `tests/test_foucault_workflows.py`.
- Accept `!` exclusion patterns in the `paths` input. A pull request that
  touches only excluded files gets a skipped check and no model call. The
  foucault and euler self-reviews exclude the root `CHANGELOG.md` and
  `README.md`.
- Honor a `<persona>-scan-requested` label. A labeled pull request passes
  the `paths` filter of that persona. The foucault and euler self-reviews
  also start when a person adds the matching label.
- Reuse one review per head. `engine/review_key.py` hashes the persona,
  mode, head, base, engine ref, pull request title and body, persona
  options, and chunk caps. Each published check run carries that key in
  its `external_id`. A rerun with the same key reuses an earlier failing
  check run and calls no model. A passing result always reruns. A check run
  that another workflow plants with the key never suppresses a review. The active human approved the edit to the
  existing `tests/test_review_workflow_stages.py` that admits the key step.
- Confirm each chunk BLOCK with one more run. The BLOCK stands only when
  that run blocks with a finding class from the first run. Otherwise the
  chunk records NEEDS-HUMAN. The result keeps the findings and reports of
  both runs. The active human approved the second scripted reply in the
  existing `tests/test_engine_run_review.py`.
- Add `engine/run_eval.py --repeat N`. It sends every case N times and
  reports the share of runs with the most common verdict.
- Record NEEDS-HUMAN with the findings of a retry that fails only on
  process narration or coverage lines. Any other invalid retry still fails
  the run.
- Add the `require_coverage` mode flag. A flagged review reply must open
  with the mode line, a `Scope:` line, and an `Unseen:` line. The mode
  line must name the expected mode. The foucault
  `security` and euler `quality` modes set it. The active human approved
  the opening lines added to the scripted reply in the existing
  `tests/test_euler_review_hooks.py`.
- Add an optional `format_note` to each provider profile. The note joins
  the system prompt of that profile only. The `ollama-large` profile for
  minimax-m3.1-flash carries one.

### Changed
- Drop the generay sync job from `examples/label-caller.yml`. The `sync`
  mode delivers context only. The active human approved the matching edit
  in the existing `tests/test_foucault_workflows.py`.
- Rename the labels in `examples/label-caller.yml` to
  `<persona>-scan-requested`. The file also serves a repository that wants
  manual scans only. The active human approved the new label names in the
  existing `tests/test_foucault_workflows.py`.
- Send a fixed seed to Ollama, OpenAI-compatible, and Google providers. The
  Anthropic Messages API takes no seed.
- Require coverage on two noun-only lines, `Scope:` and `Unseen:`, after the
  `**Mode:**` line. The validator rejects a line outside a code fence that
  opens with Reviewed, Examined, Inspected, Traced, Checked, Analyzed,
  Verified, Looked, Went, Started, Review covered, or The review. The
  rejection uses the existing single retry. The prompt shows the three
  opening lines and names no banned opener.
- End every provider request with a short trusted reminder after the
  review envelope. It names the opening and closing report lines.
- Add the model call command and `fail_on_block` to the review key.
- Require the hook sandbox by default. An empty
  `PERSONAS_REQUIRE_SANDBOX` or `1` fails closed without a trusted
  bubblewrap. Only `0` allows the warned local fallback.
- Run bubblewrap only from `/usr/bin/bwrap`. The engine never searches
  `PATH`. It rejects a symlink, a file not owned by root, and a file that a
  group or other user can write.
- Bind five runtime files from `/etc` in place of the whole directory:
  `ld.so.cache`, `localtime`, `nsswitch.conf`, `passwd`, and `group`.
- Set `PERSONAS_REQUIRE_SANDBOX=0` in the euler engine run test and the
  `/proc` key test only when the variable is unset. CI keeps `1`. The
  active human approved the edit to the existing
  `tests/test_euler_review_hooks.py`.

### Fixed
- Require every generay finding to cite a file and line inside the review
  target. A pull request line falls inside a hunk of the file patch. A
  local line falls inside the file. The line must be a positive integer.
  The active human approved the fixture patch in the existing
  `tests/test_generay_review_hooks.py`.
- Cap the generay registry validator at 64 nesting levels. Deeper input
  returns a validation error instead of a recursion failure.
- Name the generay registry validator's unsupported-schema exit status and
  the doc policy diagnostic excerpt width.
- Diff each review case from the merge base of base and head. A pull
  request behind its base branch no longer shows the newer base commits in
  reverse. euler reviewed a one-file probe as a 12-file change before the
  fix.

## [0.10.0] (2026-11-20)

### Added
- Run every persona hook under bubblewrap on Linux. `engine/sandbox.py`
  builds the sandbox. The hook gets no network, a private PID namespace,
  read-only system paths, Python, engine, and persona, and writable access
  to the empty home and the head tree copy only.
- `PERSONAS_REQUIRE_SANDBOX=1` fails a run closed without bubblewrap. The
  review steps set it. A local run without bubblewrap warns and falls back.
  `off` skips the sandbox for plumbing tests. The active human approved
  that value and one fixture edit in the existing
  `tests/test_engine_review_hooks.py`.
- Install bubblewrap 0.9.0-1ubuntu0.3 in the review jobs. The jobs now run on
  `ubuntu-24.04`. The active human approved the pin under Rule 9.
- Load `engine/apparmor/bwrap` before the sandbox runs. Ubuntu 24.04
  restricts unprivileged user namespaces. The profile grants `userns` to
  `/usr/bin/bwrap` only.
- Add `.github/workflows/sandbox-check.yml`. It runs the sandbox tests on
  every pull request on the pinned image.
- Start each hook with the resolved Python interpreter. uv and the runner
  toolcache reach Python through symlinked directories that the sandbox
  does not bind.
- Add injection cases for a fake prescan array in the body, an approving
  file name, and a regex excerpt that the euler prescan quotes. The excerpt
  case runs the real prescan and checks the envelope placement.
- Record decision 33 in `docs/plans/consolidation.md`.
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
- Run every persona hook through `engine/run_hook.py` in a child process
  with an allowlisted environment. The engine process never imports the
  hook file in any stage. Each child starts in an empty temporary
  directory. The same directory is its home.
- Record decision 32. Hooks keep network access and read access to the
  runner filesystem. A full sandbox stays a follow-up.
- On Linux, `engine/run_review.py` marks itself non-dumpable. The review
  step runs it through `exec`. A hook child then cannot read
  `MODEL_API_KEY` from `/proc`. The fix also allows the variable macOS
  adds to every process in the environment test.
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
- The euler reply CLI reads the engine envelope layout and the euler eval
  layout.
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
