# Template drift

This file records local differences from the `abuzucom/agents` template.
The template revision is `e05985f21a78780bc1758e9bfe008c15a1d26832` (v2.50.0).
The previous revision was `4797f1441eefb6c082dadea3130d28021b30f9a9` (v2.46.0).

## Taken

- `AGENTS.md` and all eight synchronized copies. `scripts/sync.py` generates
  the copies.
- Every file under `scripts/`, `hooks/`, and `tools/hook-trace/`.
- Every skill under `skills/`, `.claude/skills/`, and `.agents/skills/`.
- `docs/enforcement-matrix.md`.
- Every file under `tests/` except the modules listed below.
- `.claude/settings.json`, `.codex/config.toml`, `.codex/hooks.json`,
  `.gemini/settings.json`, and `.agents/hooks.json`.
- `shared-files.json`, `hook-coverage-baseline.json`, and
  `.local-path-allowlist`.
- `.gitattributes`, `.editorconfig`, `.claudeignore`,
  `.pre-commit-config.yaml`, `requirements-checkers.txt`, and `Makefile`.
- `docs/agent-policy/adoption.md`, `enforcement.md`, `clients.md`,
  `github.md`, and `security.md`.
- `.github/workflows/sync-check.yml`, `agents-compliance.yml`,
  `agents-md-compliance.yml`, `gate-integrity.yml`, and
  `immutable-conflict-check.yml`.

## Declined

- The template `.github/workflows/release.yml`, `policy-size-report.yml`, `security-review-pr.yml`,
  `quality-review-pr.yml`, and `persona-review-labels.yml`. The source
  repository owns these workflows.
- The template `hooks/workflow-scripts.local.txt`. It lists the source
  `scripts/release.py` forms.
- `ci/`. Plan step 3 moves the review engine into `engine/`.
- `docs/agent-policy/source-orientation.md`, `DRIFT.md`, `adopters/`,
  `policy-digests.json`, and `plan/`. These belong to the source repository.
- The test modules below read declined files. The active human approved the
  omission of each module. No adopted test changed.

| Module | Declined dependency |
|---|---|
| `test_check_conflict_markers.py` | source `README.md`, `plan/` |
| `test_scan_and_hash_wiring.py` | checker installs in declined workflows |
| `test_policy_distribution.py` | source local policy block in `AGENTS.md` |
| `test_policy_marker_names.py` | `source-orientation.md` |
| `test_policy_size_report_hardening.py` | `policy-size-report.yml` |
| `test_policy_size_report_wiring.py` | `policy-size-report.yml` |
| `test_quality_review_wiring.py` | `quality-review-pr.yml` |
| `test_security_review_wiring.py` | `security-review-pr.yml` |
| `test_review_adapter_portable.py` | `ci/` |
| `test_release_assets.py` | `release.yml`, release assets |
| `test_release_build_target.py` | `release.yml`, release assets |
| `test_release_bundle_signer.py` | `release.yml` |
| `test_release_draft_lookup.py` | `release.yml` |
| `test_release_draft_refresh.py` | `release.yml` |
| `test_release_hardening.py` | `release.yml`, source `README.md` |
| `test_release_latest_stable.py` | `release.yml` |
| `test_release_workflow_wiring.py` | `release.yml` |
| `test_review_verdict_producer.py` | `security-review-pr.yml`, `quality-review-pr.yml` |
| `test_source_publishing_scripts.py` | source `hooks/workflow-scripts.local.txt` |
| `test_persona_label_review_wiring.py` | `persona-review-labels.yml` |

## Current drift

- `.github/workflows/release.yml` is a local workflow. It replaces the
  declined template workflow of the same name. `tools/release_personas.py`
  builds its files. The template `scripts/release.py` stays unused. The
  template `test_release_*.py` modules stay declined.
- `.compliance-tree-exemptions.json` is a local manifest. It lists the
  five `*-review-pr.yml` callers and `stop-requested-notice.yml` for the
  reviewed `pull_request_target` rule set of
  `scripts/check_compliance_tree.py`. Each entry pins the workflow
  SHA-256 and the bound wrapper SHA-256. A caller or wrapper edit needs a
  matching manifest pin. `reviewers/*/eval/cases/` skips the Rule 7 scan.
  The eval cases hold planted defects. The active human approved each
  entry on 2026-11-26.
- 447 persona and engine test names shrink to at most five words after
  `test_`. Two test comments drop personal pronouns. The adopted
  `tests/test_check_all_test_names.py` enforces both rules. Names changed.
  Test bodies and assertions stayed the same. The active human approved the
  renames under Rule 3 on 2026-11-25.
- `AGENTS.md` holds the policy section of `--print-adoptable` output only.
  That output also appends `docs/agent-policy/` and orientation files.
  `scripts/sync.py` appends those files again during copy generation. An
  unmodified copy of the full output exceeds the 64 KiB policy size limit.
- `docs/project-orientation.md` stays below 404 bytes. Assembly appends it to
  the policy. The template policy leaves 403 bytes below the 64 KiB limit.
- `tests/test_adopter_branch_fixtures.py` holds an unchanged copy of the
  portable `CiBranchFixtureTest` class from the adopted
  `test_ci_branch_fixtures.py`.
  That class gives hook coverage of the valid-branch paths in
  `hooks/enforce_branch_name.py`.
- `Makefile` names this repository's prose files in `PROSE_FILES`.
- `Makefile` adds the `lint-code` target. The target runs ruff, mypy, and
  yamllint from `requirements-dev.txt` over the engine, the personas, the
  matching tests, and the workflows this repository owns. `make lint` stays
  standard-library only.
- `hooks/workflow-scripts.local.txt` holds a review engine section and a
  persona section. The active human approved the persona entries under
  Rule 22 on 2026-11-22. The active human approved the move from the shared
  list on 2026-11-26. `tests/test_engine_script_gate.py` and
  `tests/test_persona_script_gate.py` cover both sections.
- `scripts/check_agent_prose_gate.py` names the same prose files in
  `TARGET_FILES`. `tests/test_check_agent_prose_gate.py` requires that list
  to match `sync-check.yml`.
- `sync-check.yml` names this repository's prose files in the prose and
  ASCII steps. The workflow omits the template-file ASCII step. This
  repository holds none of those template files.
- `.claudeignore` drops the JavaScript entries. This repository holds Python
  only.
- `hook-coverage-baseline.json` is the template file without regeneration.
  `--write-baseline` refuses to run as root. The adopting environment ran as
  root. Every file under `hooks/` is byte-identical to the template.
