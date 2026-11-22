# Consolidate PR checkers into abuzucom/agents-personas

## Context

Five PR checker repos each carry a drifted copy of the agents policy and the same review plumbing:

| Repo | Reviewer | Prompt | Reusable workflow | Version |
|---|---|---|---|---|
| foucault | security | `AUDIT.md` | `security-review.yml` | 3.8.9 |
| euler | code quality | `QUALITY.md` | `quality-review.yml` | 0.9.1 |
| adorno | UI/UX, a11y | `AUDIT.md` + bundles | `ui-review.yml` | unreleased |
| generay | time/date | `TIME.md`, `SYNC.md` | `time-review.yml` | 0.3.1 |
| havel | privacy | regime bundles | `privacy-review.yml` | unreleased |

Survey findings that drive the design:

- All five are Python with a `workflow_call` workflow, a model call, a `VERDICT:` contract, and an `eval/` harness. None has an `action.yml`, a `.pre-commit-hooks.yaml`, or a package manifest.
- The review engine has diverged three ways:
  - foucault uses `ci/build_pr_case.py` + `ci/run_model_command.py` (argument-array `subprocess.run`, `shell=False`).
  - euler and generay use `ci/run_review.py` + `ci/check_review_response.py` + `scripts/review_{envelope,report}.py`.
  - adorno and havel run `eval "$MODEL_CALL_COMMAND"` in the workflow. That command violates Rule 1.
- Policy copies in all five lag agents. foucault stops at Rule 20. generay lacks Rule 24. adorno and havel pin `e6ddde18`. euler is hand-tailored. About 25 `scripts/check_*.py` per repo duplicate agents checkers with drift.
- agents has no module system. Adoption is a manual copy procedure in `README.md:275-435`. `check_gate_adoption.py` and `complete_gate_adoption.py` require the full gate set.
- agents `gate-integrity.yml` requires a human-applied `gate-change-approved` label on every workflow change. agents bumps SemVer on every change.

The active human accepted breaking public API changes. Callers switch `uses:` targets and inputs. No compatibility shims.

## Decisions (2026-11-19)

| # | Topic | Decision |
|---|---|---|
| 1 | Topology | Separate reviewers repo. agents keeps policy and gates. |
| 2 | Name | `abuzucom/agents-personas` |
| 3 | Selection | Clients and advisory checkers only. Gate core stays whole per client. |
| 4 | History | Copy with provenance. Source history stays in the old repos. |
| 5 | Lint deps | Carry ruff, mypy, yamllint. Pin ruff 0.17.4. Exact pins get Rule 9 approval at execution. |
| 6 | Engine copies in agents | Delete after repoint. Rule 2 consent immediately before the act. |
| 7 | Old repos | Freeze with a README pointer. No archive. |
| 8 | Pilot | foucault (security) |
| 9 | Plan home | `docs/plans/consolidation.md` in agents-personas. A pointer from the agents README lands in step 9 or 10. |
| 10 | Side issues | Two agents policy doc fixes run as separate tasks. havel prompt path and action pins fold into steps 8 and 3. |
| 11 | Persona names (2026-11-20) | Each reviewer keeps the name of its source repo. Directories, `persona` values, and eval flags use the persona name. Wrapper workflows use `<persona>-<function>-review.yml`, for example `foucault-security-review.yml`. |
| 12 | Persona modes (2026-11-20) | Each persona declares modes in `reviewer.json`. A mode supports review delivery, context delivery, or both. Wrappers take a `modes` input that defaults to the persona's default mode. Each adopter caller workflow chooses the pull requests for extra modes. |
| 13 | Secrets (2026-11-20) | The secrets interface stays unchanged. Each wrapper declares the exact secret names, required flags, and environment of the source workflow it replaces. Adopter repository secrets and `secrets:` mappings stay unchanged. |
| 14 | Fork runs (2026-11-20) | The engine applies one fork rule to every persona. A fork pull request gets a visible skipped check per requested mode and no secret. `fork_review: true` runs the review under the `fork-review` environment after a person approves. The engine never executes fork code with a secret in scope. |
| 15 | Review output (2026-11-20) | Each run posts a new comment per head SHA and mode in the euler layout. A verdict heading opens the visible comment. A hidden marker line identifies the run. Each mode also gets a check run with line annotations. |
| 16 | Verdict values (2026-11-20) | The engine accepts `APPROVE`, `BLOCK`, and `NEEDS-HUMAN`. All five source validators accept the same set. |
| 21 | Non-gating verdicts (2026-11-20) | `NEEDS-HUMAN` always sets the mode check to `neutral` and emits a run warning. It never blocks CI. `fail_on_block` gates `BLOCK` only. With `fail_on_block: false`, `BLOCK` also concludes `neutral`. |
| 22 | Action pins (2026-11-20) | Engine workflows pin checkout v7.0.1, setup-python v7.1.0, github-script v9.0.0, and upload-artifact v7.0.2 at the euler and generay SHAs. |
| 17 | Engine hardening (2026-11-20) | Fenced untrusted content, a shared injection corpus, one resolve job, one provider table, per-mode caps, timeouts with one retry, and usage in each check. |
| 18 | Evals and data (2026-11-20) | CI runs eval structure checks only. Live model evals run locally through `engine/run_eval.py`. The `eval-live` CI job left the plan on 2026-11-21. Each persona carries `DATA.md`. |
| 19 | Adopters and releases (2026-11-20) | `docs/migration.md` and `examples/` guide adopters. The active human moves each repo. One repo SemVer with per-persona notes. |
| 20 | Persona template and metrics (2026-11-20) | `reviewers/_template/` scaffolds new personas. Each run writes a metrics step summary. |
| 23 | Caller patterns (2026-11-20) | foucault and euler run on every pull request through a `workflow_run` caller after CI. Branch protection requires both checks. adorno, generay, and havel run through a `pull_request_target` caller on `labeled`, `synchronize`, and `unlabeled`. Each job checks its own `<persona>-scan-requested` label. The `stop-requested` label skips every persona. Those checks stay optional. `examples/always-on-caller.yml` and `examples/label-caller.yml` show both. |
| 24 | Path filter (2026-11-20) | `review.yml` and every wrapper take an optional `paths` input of newline-separated globs. A pull request without a matching changed file gets a skipped check named "No matching files". No `enabled` input exists. |
| 25 | Finding rules (2026-11-20) | A review mode can declare `finding_rules` in `reviewer.json`. The block names the exact finding keys, the allowed severities, and a class prefix. The shared validator enforces each rule. foucault declares five keys, CRITICAL to LOW, and the `2.` prefix. |
| 26 | Local modes (2026-11-20) | Each persona keeps its workstation modes, for example foucault File, Piece, and Wholesale. A mode with `local: true` has no CI delivery. `verdict_line` and `verdicts` name its verdict form. `json_mode` names the mode string the prompt expects. All source eval cases move into `eval/cases/<mode>/`. |
| 27 | Eval runner (2026-11-20) | `engine/run_eval.py` checks case structure for every mode and grades live replies through `--model-call`. The engine grades the verdict line, `REVIEW STATUS`, and `VERDICT_JSON`. A persona adds its own checks in `eval/extra_checks.py` through `validate_expected`, `build_model_input`, and `grade_response`. |
| 28 | Review hooks (2026-11-20) | A persona can ship `review_hooks.py` with `case_context`, `validate_reply`, and `forced_verdict`. The engine writes the head tree from git objects for `case_context` and executes none of it. A blob over 1 MiB stays unwritten. A tree over 64 MiB skips the hook and marks every changed file unreviewed. Hook items can quote pull request text, so they join `REVIEW_TARGET`, never `TRUSTED_CONTEXT`. The changed and unreviewed path lists join `REVIEW_TARGET` too. Trusted metadata keeps their counts. A tree listing over 100,000 entries or 16 MiB stops the read and skips the hook. euler's prescan, QUALITY.md reply rules, and prescan BLOCK use these hooks. |
| 29 | Persona options (2026-11-20) | `review.yml` takes one `persona_options` JSON object. `reviewer.json` declares each option with a type and a default. The engine rejects undeclared options. euler declares `exclude_paths`. |
| 30 | Build stage (2026-11-20) | Each review job builds the case in a step without the provider key, then reviews it in the key step. Every persona hook runs in a child process with an allowlisted environment in every stage. Persona hook code never runs beside the key. The review step rejects a built case for other inputs. |
| 31 | Lint toolchain (2026-11-20) | ruff, mypy, and yamllint from decision 5 land in a separate pull request after the euler step. |
| 32 | Hook isolation limit (2026-11-20) | A persona hook child gets an allowlisted environment and an empty temporary directory as its working directory and home. It keeps network access and read access to the runner filesystem. Decision 33 closes the network and filesystem gap on Linux. Checkouts persist no credential, and the token reaches only the fetch step. On Linux the engine marks itself non-dumpable, and the review step runs it through `exec`, so a hook cannot read the key from `/proc`. |
| 33 | Hook sandbox (2026-11-20) | On Linux every persona hook runs under bubblewrap 0.9.0-1ubuntu0.3, pinned under Rule 9 on `ubuntu-24.04`. The sandbox unshares the network and the PID namespace. It binds `/usr`, the Python installation, `engine/`, and the persona read-only. From `/etc` it binds only `ld.so.cache`, `localtime`, `nsswitch.conf`, `passwd`, and `group`. Only the empty home and the head tree copy are writable. An AppArmor profile in `engine/apparmor/bwrap` grants `userns` to bwrap only, since Ubuntu 24.04 restricts user namespaces. The engine runs only `/usr/bin/bwrap` and never searches `PATH`. That file must be a root-owned regular file that no group or other user can write. The engine requires the sandbox by default (2026-11-21). An empty value or `1` fails closed without a trusted bwrap. Only `PERSONAS_REQUIRE_SANDBOX=0` allows a warned local fallback to the plain child. `off` serves plumbing tests only. Any other value fails closed. `sandbox-check.yml` proves the sandbox on every pull request. macOS and Windows keep the plain child. |
| 34 | Review variance (2026-11-21) | Identical runs of one model can disagree on a verdict. Four controls narrow that spread. The workflow reuses a failing check run with the same review key. A label event or a rerun on those inputs then calls no model. The key in `engine/review_key.py` covers the persona, mode, head, base, engine ref, pull request title and body, persona options, and chunk caps. Providers with a seed parameter receive a fixed seed. A chunk BLOCK stands only when one confirmation run blocks with a repeated finding class. Otherwise the chunk records NEEDS-HUMAN. Either way the chunk keeps the findings and reports of both runs. `engine/run_eval.py --repeat N` measures the agreement rate. The report contract forbids coverage narration and states coverage on the `Scope:` and `Unseen:` lines. The prompt shows those opening lines and names no banned opener. A trusted reminder ends each user message. A provider profile can add a `format_note` for its model. A review mode with `require_coverage` must open with the mode line, `Scope:`, and `Unseen:`. The foucault and euler review modes set it. A retry that fails only on narration or coverage records NEEDS-HUMAN with its findings. The review key also covers the model call command and `fail_on_block`. The job concurrency group cancels an earlier run for the same pull request and mode. Two runs therefore never both finish a model call. Any workflow with `checks: write` in the caller repository can create a check run with a matching key. Branch protection passes success and neutral. The cache reuses only failure. A planted check run therefore never suppresses a review. |
| 35 | generay port (2026-11-21) | generay moves to `reviewers/generay` from `abuzucom/generay` at `309d425`. The `time` review mode loads `TIME.md` and `SYNC.md` through a prompt list and requires the coverage lines. The `sync` mode delivers context only. The local `file`, `piece`, `wholesale`, and `contract` modes keep the generay verdict lines. The time prescan runs as the `case_context` hook and places advisory candidates in `REVIEW_TARGET`. The `validate_reply` hook applies the generay reply rules. generay defines no `forced_verdict`. The wrapper requires `MODEL_API_KEY`. This repository self-reviews with generay only under the `generay-scan-requested` label. The label example drops the generay sync job. |
| 36 | adorno port (2026-11-22) | adorno moves to `reviewers/adorno` from `abuzucom/adorno` at `97a2c84`. Every mode loads the prebuilt `bundles/ui-full.md`. A test rebuilds the bundle and requires a byte-for-byte match. The `ui` review mode requires the coverage lines and applies the `2.` class finding rules. The local `file`, `piece`, `wholesale`, and `design-spec` modes keep the adorno verdict lines. The wrapper keeps `MODEL_API_KEY` optional. This repository self-reviews with adorno only under the `adorno-scan-requested` label. |

## Two repos

- `abuzucom/agents` holds policy, gates, clients, and generic checkers. It keeps that role and gains client and advisory-checker selection.
- `abuzucom/agents-personas` holds all five reviewers plus one shared review engine. It adopts agents like any other repo.

Reasons:

- Reviewer prompts and eval cases change often. In agents each change would trip the gate-integrity label, the policy-size check, and a SemVer bump.
- Reviewer workflows need `pull-requests: write`, `checks: write`, model API key secrets, a `fork-review` environment, and `workflow_run` triggers. Keeping those out of agents keeps its privileged surface small.
- Adopters go from six pins to two.
- Six policy copies become two.

## agents-personas layout

```
reviewers/
  foucault/   security: AUDIT.md, eval/cases/, check_audit_policy.py, docs
  euler/      code quality: QUALITY.md, quality_checks/, eval/cases/
  adorno/     UI/UX, a11y: AUDIT.md, bundles.json, bundles/, eval/cases/
  generay/    time/date: TIME.md, SYNC.md, time_checks/, data/libraries*.json,
              eval/cases/time/, eval/cases/sync/
  havel/      privacy: regimes/, bundles.json, check_regime_refs.py
  <name>/reviewer.json   modes, prompt files, bundles, extra inputs, permissions, secrets
engine/
  build_pr_case.py, run_model_command.py, call_model.py,
  check_review_response.py, review_envelope.py, review_report.py,
  build_bundle.py, run_eval.py, model_providers.json,
  check_reviewers.py, render_context.py
.github/workflows/
  review.yml             reusable engine, input `persona`
  foucault-security-review.yml, euler-quality-review.yml,
  adorno-ui-review.yml, generay-time-review.yml,
  havel-privacy-review.yml   thin reusable wrappers
policy files             synced from agents via scripts/sync.py
```

## Unified review engine

- Base the engine on foucault's argument-array runner (`ci/run_model_command.py`). Fold in euler's chunking, envelope, and report code.
- Replace adorno and havel `eval "$MODEL_CALL_COMMAND"` with the runner.
- Build one response validator from `check_pr_review_response.py` and euler `ci/check_review_response.py`.
- Use one `run_eval.py --persona <name>`, for example `--persona foucault`. Eval cases live per persona.
- The `persona` input takes `foucault`, `euler`, `adorno`, `generay`, or `havel`.
- Use one `build_bundle.py` (havel origin) for adorno and havel.
- Common inputs on every persona workflow:
  - `personas_ref` (replaces `audit_ref`, `quality_ref`, `time_ref`)
  - `pr_number`, `base_sha`, `head_sha`
  - `model_call_command`, `pr_comment`, `fail_on_block`, `fork_review`
  - `modes`, a comma-separated mode list that defaults to the persona's default mode
- Persona-specific inputs stay on the wrappers: `regimes` for havel, and `exclude_paths` and `max_chunks` for euler and generay.
- Adopters pick reviewers with one `uses:` line per persona, all at the same `agents-personas@<sha>`.

### Secrets

- Each wrapper declares the same secret names as the source workflow it replaces. foucault and euler declare `MODEL_API_KEY`. The `abuzucom/agents` callers map it from `OLLAMA_API_KEY`.
- Each persona step records the secret names of the source workflow before the import. The wrapper keeps those names.
- A persona without a pull request workflow today gets one in its persona step. Its wrapper declares `MODEL_API_KEY` like the wired personas. No new secret name appears.
- Required and optional flags and the `fork-review` environment stay unchanged.
- `review.yml` receives the key from the wrapper. Adopters change only the `uses:` line.
- Each wrapper test asserts the exact secret names and environment of the source workflow. A rename fails CI.

### Fork runs

Current callers in `abuzucom/agents` run on `workflow_run`. Default branch code reviews every pull request. A resolve step sets `same_repository`. Fork pull requests get no model review and no secret today:

- `security-review-pr.yml` prints a skip message in a log line. It creates no check.
- `quality-review-pr.yml` creates a `quality-review` check with conclusion `skipped`.

The engine replaces both forms with one rule:

- A fork pull request gets a `skipped` check for each requested mode, for example `generay / time`. The check title reads "Skipped for fork pull request".
- `fork_review: true` runs the review job under the `fork-review` environment. The repository owner sets required reviewers on that environment. A person approves each fork run before the secret reaches the job.
- The engine reads the fork diff as data through the GitHub API. It never checks out or executes fork code with a secret in scope. The reviewer always runs from the pinned default branch.
- The wrapper keeps the `fork_review` input and the `fork-review` environment names (decision 13).
- Tests assert a skipped check per mode with no secret for a fork. Tests assert the `fork-review` environment on the opt-in job. Tests assert that no step checks out the fork head with a secret in scope.
- Each persona step records the source workflow behavior for `fork_review` before the import. The pull request for that step names any difference.

### Modes

`reviewer.json` declares a `modes` map. generay shows the shape:

```json
{
  "modes": {
    "time": { "prompt": ["TIME.md", "SYNC.md"], "review": true, "default": true },
    "sync": { "prompt": "SYNC.md", "context": true }
  }
}
```

- `review: true` lets the engine run the mode on a pull request with a verdict.
- `context: true` lets `engine/render_context.py --persona <name> --mode <mode>` print the mode for an agent context. That command replaces the manual SYNC paste.
- `local: true` keeps a mode for workstation runs through `engine/run_eval.py` only (decision 26).
- Each persona has exactly one default mode. A single-mode persona declares one entry.
- A mode prompt names one file or a list of files. The engine joins a list in order. The generay time mode loads `TIME.md` and `SYNC.md` together.
- Each review mode runs as a separate check with a separate verdict, for example `generay / time`. Branch protection can require each check alone. The generay `sync` mode delivers context only and posts no check.
- `engine/check_reviewers.py` validates every `reviewer.json`. It rejects a missing default, a missing prompt file, and a mode without delivery. The engine rejects an unknown mode and a mode without review delivery.
- Eval cases live in `reviewers/<name>/eval/cases/<mode>/`. `run_eval.py --persona <name> --mode <mode>` runs the cases of one mode. Context modes get render checks for stable output, ASCII, and size.
- The engine holds no persona-specific branch. A new mode for any persona adds one entry and its eval cases.

An adopter runs generay on chosen pull requests:

```yaml
jobs:
  generay:
    if: contains(github.event.pull_request.labels.*.name, 'generay-scan-requested')
    uses: abuzucom/agents-personas/.github/workflows/generay-time-review.yml@<sha>
```

The caller condition can use a label, a `paths:` filter, or a base branch. A person applies any label. Agents never apply labels (Rule 23).

Automatic context injection of a context mode stays out of this plan. It needs hook changes under Rule 22 in `abuzucom/agents`.

### Review output

Each run publishes three outputs per requested mode:

- A check run named `<persona> / <mode>` with the verdict and a summary. Branch protection can require each check.
- Line annotations on the check run for findings tied to changed lines.
- A new pull request comment. The engine never edits an earlier comment. A rerun on the same head SHA and mode posts no second comment. The `already_reviewed` lookup enforces that limit.

Every persona posts the euler comment layout (revised 2026-11-20):

```
<!-- persona-review: <persona> / <mode> | head <sha> -->
## <Persona> <mode> review: <VERDICT>

Base `<sha>`. Head `<sha>`.
Workflow run: <url>

### Chunk 001: <VERDICT>
<fenced chunk report>
```

GitHub renders no HTML comment. The hidden first line lets the `already_reviewed` lookup find an earlier comment for the same head and mode.

### Verdicts

Source record (2026-11-20):

| Repo | Accepted values | `fail_on_block` default | Non-gating `BLOCK` |
|---|---|---|---|
| foucault | `APPROVE`, `BLOCK`, `NEEDS-HUMAN` | true | job passes |
| euler | `APPROVE`, `BLOCK`, `NEEDS-HUMAN` | true | check `neutral` |
| adorno | `APPROVE`, `BLOCK`, `NEEDS-HUMAN` | true | job passes |
| generay | `APPROVE`, `BLOCK`, `NEEDS-HUMAN` | true | check `neutral` |
| havel | `APPROVE`, `BLOCK`, `NEEDS-HUMAN` | true | job passes |

`REJECT` appears in the sources only as a malformed-token test fixture.

- One response validator enforces `APPROVE`, `BLOCK`, and `NEEDS-HUMAN` for every persona and mode (decision 16).
- `fail_on_block` defaults to true. A true value fails the mode check on `BLOCK`. A false value sets the check to `neutral` (decision 21).
- `NEEDS-HUMAN` concludes `neutral` whatever `fail_on_block` says. The run shows a warning annotation. Capacity limits and unreviewed files record `NEEDS-HUMAN`, so both warn without blocking.
- A run without a valid verdict never reports a pass.

### Untrusted pull request content

- The envelope fences the diff, title, body, and file names as data. The prompt states that fenced content carries no instructions.
- The engine caps the size of each fenced field.
- A shared corpus under `engine/eval/injection/` holds adversarial cases, for example diff text that orders an approval. Every review mode must pass the corpus.

### Shared resolve job

One reusable job in `review.yml` resolves the pull request for every persona. It outputs the pull request number, base and head SHAs, `same_repository`, and `already_reviewed`. Callers stop copying the resolve script.

### Evals in CI

- Eval structure checks run on every pull request.
- Live model evals run locally through `engine/run_eval.py`. No CI job calls a model for evals.

### Data handling

- The plan rule states that a persona sends the provider only the fenced pull request content and the persona prompt.
- Each `reviewers/<name>/DATA.md` lists the content that persona sends.
- havel sends no secrets and no personal data. havel's `DATA.md` states the exclusion and its test.

### Model providers and cost

- `engine/model_providers.json` holds the single provider table. Each `reviewer.json` names a provider and model.
- Each mode in `reviewer.json` sets token and chunk caps. A wrapper input can lower a cap. A wrapper input never raises one.
- Each provider request has a fixed timeout and one retry. A run without a verdict after the retry never reports a pass.
- Each check run summary lists the tokens and chunks used.

### Run metrics

Each run writes a step summary with the verdict, the duration, and the token count per mode.

### Persona template

`reviewers/_template/` holds the scaffold for a new persona. `check_reviewers.py` validates the scaffold. A sixth persona copies the template and fills `reviewer.json`, the prompts, `DATA.md`, and eval cases.

### Adopter migration

- `docs/migration.md` maps each old `uses:` line and input to the new wrapper and input. Example: `audit_ref` maps to `personas_ref`.
- `examples/always-on-caller.yml` and `examples/label-caller.yml` hold the copy-paste callers (decision 23). Each persona step adds a job to one of the two files.
- Secrets stay unchanged (decision 13).
- The active human moves each adopter repo to the new callers. The plan holds no automated cutover or rollback. Old callers keep working on old repo SHAs until that move.

### Releases

- agents-personas uses one SemVer version in `CHANGELOG.md`.
- Each release entry holds one section per changed persona.
- A person creates every tag and release. Agents never create tags or releases.

## agents changes

- Make the clients selectable. The set covers claude, codex, gemini, and antigravity.
- Make the advisory checkers selectable. The set covers the prose bundle, spelling, english-only, and hedging.
- Always install the canonical policy, `docs/agent-policy/`, and the blocking gate core for each selected client.
- Adopter manifest `agents.adopt.json` with `agents_ref`, `clients`, and `advisory`. `scripts/adopt.py --manifest agents.adopt.json` stages files under `.gate-staging/` and hands off to `complete_gate_adoption.py`. With no manifest, the full set applies.
- Remove agents' copies of foucault engine files (`ci/build_pr_case.py`, `ci/call_model.py`, `ci/run_model_command.py`, `ci/model_providers.json`, `scripts/check_pr_review_response.py`) after the repoint. This needs Rule 2 consent.
- Repoint agents `security-review-pr.yml` and `quality-review-pr.yml` to agents-personas.

## Migration order

One draft PR per step.

1. Done 2026-11-19. The active human created `abuzucom/agents-personas`.
2. Adopt the agents policy into agents-personas.
3. Build the engine. Move the agents `ci/` copies plus euler chunking into `engine/`. Add `review.yml`. Add the mode schema, `check_reviewers.py`, `render_context.py`, and one check per mode. Add the fork rule, the shared resolve job, the review outputs, the provider table, the caps, the injection corpus, and `reviewers/_template/`. Write tests first. Use the decision 22 pins. Step 3 lands as three draft PRs:
   - 3a adds the decisions record and the mode schema in `engine/reviewers.py`. It also adds `engine/check_reviewers.py`, `engine/render_context.py`, and `reviewers/_template/`. Done 2026-11-20.
   - 3b-1 adds the provider table, the model adapter with usage, the argument-array adapter runner, and the shared response validator.
   - 3b-2 adds the fenced envelope, the caps, the chunking, and the injection corpus. The euler prescan moves with the euler persona in step 5.
   - 3c-1 adds `engine/run_review.py` and `engine/review_output.py`. The runner reviews one mode, retries one invalid reply, and combines the chunk verdicts. The renderer builds the check conclusion, the annotations, the comment, and the metrics.
   - 3c-2 adds `review.yml`. The workflow covers the resolve job, the fork rule, the per-mode checks, the comments, and the run metrics. `personas_ref` is a required full SHA. Only the head fetch step receives the token. Python 3.14 runs every step.
4. foucault persona (security). This is the pilot. It adds the `paths` input, `finding_rules`, local modes, `engine/run_eval.py`, the wrapper, the self-review caller, and both caller examples.
5. euler persona (code quality). It adds review hooks, `persona_options`, the build stage, the wrapper, and the self-review caller.
6. generay persona (time/date). Migrate `time` as the default review mode. Migrate `sync` as an opt-in review mode with context delivery. Add eval cases for both modes and a caller example with a conditional sync job.
7. adorno persona (UI/UX, a11y).
8. havel persona (privacy). Resolve the prompt source mismatch: `privacy-review.yml:135` loads `.havel/AUDIT.md`, while the README points to `bundles/`. Add a failing test first.
9. In agents, repoint the review callers, remove the engine copies, and add a README pointer to agents-personas.
10. agents: module manifest and `scripts/adopt.py`, plus a README rewrite.
11. Freeze the five old repos. Add a README pointer to the new wrapper and `docs/migration.md`. Add a final CHANGELOG entry. A person publishes a final release. Do not archive the old repos.

Each persona step wires the persona to run on pull requests. Some personas have no pull request wiring today. The step adds the wrapper, a caller example, and a live run on a sample pull request.

Import per persona:

- prompts
- eval cases
- persona-specific scripts with tests
- a `DATA.md`, a `docs/migration.md` section, and a job in an `examples/` caller

Do not import:

- each repo's `AGENTS.md` and client copies
- `hooks/`
- duplicated `check_*.py`
- `sync.py`, `shared-files.json`, and `upstream-files.json`
- `template-drift.md`

Each import commit names its source repo and commit SHA.

agents-personas reaches 1.0.0 once the workflow contract is stable. agents takes a major bump only if step 10 changes its adoption contract.

## Gates and consent

- agents `gate-integrity.yml` needs a label on steps 9 and 10. Agents never apply labels (Rule 23).
- Rule 22 consent before hook registrations.
- Rule 9 approval of the exact ruff, mypy, and yamllint pins.
- Rule 2 consent before removing the agents engine copies.
- Rule 3 consent before any edit to an existing test.
- Each clone needs a repo-local noreply identity confirmed before its first commit.

## Verification

- Run `python scripts/run_tests.py` and `make lint PYTHON=python`.
- Run `python scripts/sync.py --check` and `--check-shared`.
- Run `check_gate_adoption.py`, `check_hook_launchers.py`, `check_hook_coverage.py`, `check_persist_credentials.py`, and `check_action_pins.py`.
- Per persona, run the eval structure check and a live workflow run on a sample PR.
- End to end, use a scratch adopter repo with `agents.adopt.json` and two persona workflows.
