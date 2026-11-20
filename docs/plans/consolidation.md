# Consolidation plan

This plan moves five PR reviewer repositories into `abuzucom/agents-personas`.
All five reviewers run on one shared review engine.

## Context

Five PR checker repositories each carry a drifted copy of the agents policy
and the same review plumbing.

| Repository | Reviewer | Prompt | Reusable workflow | Version |
|---|---|---|---|---|
| foucault | security | `AUDIT.md` | `security-review.yml` | 3.8.9 |
| euler | code quality | `QUALITY.md` | `quality-review.yml` | 0.9.1 |
| adorno | UI/UX and accessibility | `AUDIT.md` and bundles | `ui-review.yml` | unreleased |
| generay | time and date | `TIME.md`, `SYNC.md` | `time-review.yml` | 0.3.1 |
| havel | privacy | regime bundles | `privacy-review.yml` | unreleased |

Survey findings:

- All five use Python with a `workflow_call` workflow, a model call, a
  `VERDICT:` contract, and an `eval/` harness.
- None has an `action.yml`, a `.pre-commit-hooks.yaml`, or a package
  manifest.
- The review engine has three variants:
  - foucault uses `ci/build_pr_case.py` and `ci/run_model_command.py`. The
    runner uses argument-array `subprocess.run` with `shell=False`.
  - euler and generay use `ci/run_review.py`, `ci/check_review_response.py`,
    and `scripts/review_envelope.py` with `scripts/review_report.py`.
  - adorno and havel run `eval "$MODEL_CALL_COMMAND"` in the workflow. That
    form violates Rule 1.
- The policy copies in all five lag the agents policy:
  - foucault stops at Rule 20.
  - generay lacks Rule 24.
  - adorno and havel pin agents commit `e6ddde18`.
  - euler carries a hand-tailored subset.
- About 25 `scripts/check_*.py` files per repository duplicate agents
  checkers with drift.
- agents has no module system. Adoption follows a manual copy procedure in
  the agents `README.md`.
- agents `gate-integrity.yml` requires a human-applied
  `gate-change-approved` label on every workflow change.
- agents advances SemVer on every change.

The active human accepted breaking public workflow contracts. Callers switch
`uses:` targets and inputs. No compatibility shims exist.

## Decisions

The active human made these decisions on 2026-11-19.

| # | Topic | Decision |
|---|---|---|
| 1 | Topology | A separate reviewer repository. agents keeps policy and gates. |
| 2 | Name | `abuzucom/agents-personas` |
| 3 | Selection | Clients and advisory checkers only. The gate core stays whole per client. |
| 4 | History | Copy with provenance. Source history stays in the old repositories. |
| 5 | Lint dependencies | Carry ruff, mypy, and yamllint. Pin ruff 0.17.4. Exact pins need Rule 9 approval at execution. |
| 6 | Engine copies in agents | Delete after the repoint. Rule 2 consent applies immediately before the act. |
| 7 | Old repositories | Freeze each with a README pointer. No archive. |
| 8 | Pilot | security (foucault) |
| 9 | Plan home | This file. An agents README pointer lands in step 9. |
| 10 | Side issues | Two agents policy fixes run as separate tasks. The havel prompt path and the action pins fold into steps 8 and 3. |

## Two repositories

- `abuzucom/agents` holds policy, gates, clients, and generic checkers. It
  gains client and advisory checker selection.
- `abuzucom/agents-personas` holds all five reviewers plus one shared review
  engine. It adopts agents like any other repository.

Reasons:

- Reviewer prompts and eval cases change often. In agents each change trips
  the gate-integrity label, the policy size check, and a SemVer bump.
- Reviewer workflows need `pull-requests: write`, `checks: write`,
  `MODEL_API_KEY`, a `fork-review` environment, and `workflow_run`
  triggers. Separation keeps that privileged surface out of agents.
- Adopters go from six pins to two.
- Six policy copies become two.

## Layout

```
reviewers/
  security/   AUDIT.md, eval/cases/, check_audit_policy.py, docs
  quality/    QUALITY.md, quality_checks/, eval/cases/
  ui/         AUDIT.md, bundles.json, bundles/, eval/cases/
  time/       TIME.md, SYNC.md, time_checks/, data/libraries*.json
  privacy/    regimes/, bundles.json, check_regime_refs.py
  <name>/reviewer.json   prompt files, bundles, extra inputs, permissions, secret
engine/
  build_pr_case.py, run_model_command.py, call_model.py,
  check_review_response.py, review_envelope.py, review_report.py,
  build_bundle.py, run_eval.py, model_providers.json
.github/workflows/
  review.yml             reusable engine with input `persona`
  security-review.yml, quality-review.yml, ui-review.yml,
  time-review.yml, privacy-review.yml   thin reusable wrappers
```

## Shared review engine

- Base the engine on the foucault argument-array runner
  (`ci/run_model_command.py`).
- Fold in the euler chunking, envelope, and report code.
- Replace the adorno and havel `eval "$MODEL_CALL_COMMAND"` form with the
  runner.
- Build one response validator from `check_pr_review_response.py` and the
  euler `ci/check_review_response.py`.
- Use one `run_eval.py --persona <name>`. Eval cases live per persona.
- Use one `build_bundle.py` (havel origin) for ui and privacy.

Common inputs on every persona workflow:

- `personas_ref` replaces `audit_ref`, `quality_ref`, and `time_ref`
- `pr_number`, `base_sha`, `head_sha`
- `model_call_command`, `pr_comment`, `fail_on_block`, `fork_review`
- secret `MODEL_API_KEY`

Persona-specific inputs stay on the wrappers:

- `regimes` for privacy
- `exclude_paths` and `max_chunks` for quality and time

Adopters select reviewers with one `uses:` line per persona. Every line pins
the same `agents-personas` commit.

## agents changes

- Adopters select clients and advisory checkers:
  - clients: claude, codex, gemini, antigravity
  - advisory checkers: prose bundle, spelling, English only, hedging
- Every adopter receives the canonical policy, `docs/agent-policy/`, and the
  blocking gate core for each selected client.
- An adopter manifest `agents.adopt.json` names `agents_ref`, `clients`, and
  `advisory`.
- `scripts/adopt.py --manifest agents.adopt.json` stages files under
  `.gate-staging/`. It hands the candidate to `complete_gate_adoption.py`.
- A repository without a manifest receives the full set.
- agents drops its copies of the foucault engine files after the repoint:
  - `ci/build_pr_case.py`, `ci/call_model.py`, `ci/run_model_command.py`
  - `ci/model_providers.json`, `scripts/check_pr_review_response.py`
- agents repoints `security-review-pr.yml` and `quality-review-pr.yml` to
  agents-personas.

## Migration order

Each step lands as one draft PR.

1. Done 2026-11-19. The active human created `abuzucom/agents-personas`.
2. Done 2026-11-20. agents-personas adopts the agents policy at commit
   `909b93702273befaec9227ee892fe1a2261a4a41`.
3. Engine. Move the agents `ci/` copies plus the euler chunking into
   `engine/`. Add `review.yml`. Write tests first. Choose one full-SHA pin
   per action. The source repositories diverge (checkout v4.4.0 and v7.0.1,
   github-script v7.1.0 and v9.0.0). Pin changes need Rule 9 approval.
4. security persona from foucault. This step is the pilot.
5. quality persona from euler.
6. time persona from generay.
7. ui persona from adorno.
8. privacy persona from havel. Resolve the prompt source mismatch first.
   The havel workflow loads `.havel/AUDIT.md` at `privacy-review.yml:135`.
   The havel README points to `bundles/`. Add a failing test first.
9. Repoint the agents review callers. Remove the agents engine copies. Add
   an agents README pointer to agents-personas.
10. Add the agents module manifest and `scripts/adopt.py`. Rewrite the
    agents adoption README.
11. Freeze the five old repositories with a README pointer. Never archive
    the five old repositories.

Each persona import brings prompts, eval cases, persona-specific scripts,
and the tests for those scripts.

Each persona import leaves these files behind:

- the source `AGENTS.md` and client copies
- `hooks/` and duplicated `check_*.py`
- `sync.py`, `shared-files.json`, `upstream-files.json`
- `template-drift.md`

Each import commit names its source repository and commit SHA.

agents-personas reaches 1.0.0 once the workflow contract is stable. agents
takes a major bump only if step 10 changes its adoption contract.

## Gates and consent

- agents `gate-integrity.yml` needs a human-applied label on steps 9 and 10.
  Agents never apply labels (Rule 23).
- The agents-personas `gate-integrity.yml` needs the same label on every PR
  that touches gate files.
- Rule 22 consent applies before hook registration changes.
- Rule 9 approval applies to the exact ruff, mypy, and yamllint pins.
- Rule 2 consent applies before removal of the agents engine copies.
- Rule 3 consent applies before any edit to an existing test.
- Each clone needs a repository-local noreply identity before its first
  commit.

## Verification

- `python scripts/run_tests.py` and `make lint PYTHON=python`
- `python scripts/sync.py --check` and `--check-shared`
- `check_gate_adoption.py`, `check_hook_launchers.py`,
  `check_hook_coverage.py`, `check_persist_credentials.py`, and
  `check_action_pins.py`
- an eval structure check and a live workflow run per persona
- an end-to-end scratch adopter with `agents.adopt.json` and two persona
  workflows
