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
| 11 | Persona names (2026-11-20) | Each reviewer keeps the name of its source repo. Directories, `persona` values, eval flags, and wrapper workflows use the persona name. |

## Two repos

- `abuzucom/agents` holds policy, gates, clients, and generic checkers. It keeps that role and gains client and advisory-checker selection.
- `abuzucom/agents-personas` holds all five reviewers plus one shared review engine. It adopts agents like any other repo.

Reasons:

- Reviewer prompts and eval cases change often. In agents each change would trip the gate-integrity label, the policy-size check, and a SemVer bump.
- Reviewer workflows need `pull-requests: write`, `checks: write`, `MODEL_API_KEY`, a `fork-review` environment, and `workflow_run` triggers. Keeping those out of agents keeps its privileged surface small.
- Adopters go from six pins to two.
- Six policy copies become two.

## agents-personas layout

```
reviewers/
  foucault/   security: AUDIT.md, eval/cases/, check_audit_policy.py, docs
  euler/      code quality: QUALITY.md, quality_checks/, eval/cases/
  adorno/     UI/UX, a11y: AUDIT.md, bundles.json, bundles/, eval/cases/
  generay/    time/date: TIME.md, SYNC.md, time_checks/, data/libraries*.json
  havel/      privacy: regimes/, bundles.json, check_regime_refs.py
  <name>/reviewer.json   prompt files, bundles, extra inputs, permissions, secret
engine/
  build_pr_case.py, run_model_command.py, call_model.py,
  check_review_response.py, review_envelope.py, review_report.py,
  build_bundle.py, run_eval.py, model_providers.json
.github/workflows/
  review.yml             reusable engine, input `persona`
  foucault-review.yml, euler-review.yml, adorno-review.yml,
  generay-review.yml, havel-review.yml   thin reusable wrappers
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
  - secret `MODEL_API_KEY`
- Persona-specific inputs stay on the wrappers: `regimes` for havel, and `exclude_paths` and `max_chunks` for euler and generay.
- Adopters pick reviewers with one `uses:` line per persona, all at the same `agents-personas@<sha>`.

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
3. Build the engine. Move the agents `ci/` copies plus euler chunking into `engine/`. Add `review.yml`. Write tests first. Choose one full-SHA pin per action. The source repos diverge (checkout v4.4.0 vs v7.0.1, github-script v7.1.0 vs v9.0.0). Pin changes need Rule 9 approval.
4. foucault persona (security). This is the pilot.
5. euler persona (code quality).
6. generay persona (time/date).
7. adorno persona (UI/UX, a11y).
8. havel persona (privacy). Resolve the prompt source mismatch: `privacy-review.yml:135` loads `.havel/AUDIT.md`, while the README points to `bundles/`. Add a failing test first.
9. In agents, repoint the review callers, remove the engine copies, and add a README pointer to agents-personas.
10. agents: module manifest and `scripts/adopt.py`, plus a README rewrite.
11. Freeze the five old repos with a README pointer. Do not archive the old repos.

Import per persona:

- prompts
- eval cases
- persona-specific scripts with tests

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
