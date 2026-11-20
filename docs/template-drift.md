# Template drift

This file records local differences from the `abuzucom/agents` template.
The template revision is `909b93702273befaec9227ee892fe1a2261a4a41`.

## Taken

- `AGENTS.md` and all eight synchronized copies. `scripts/sync.py` generates
  the copies.
- Every file under `scripts/`, `hooks/`, and `tools/hook-trace/`.
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
  `agents-md-compliance.yml`, and `gate-integrity.yml`.

## Declined

- `.github/workflows/immutable-conflict-check.yml`, `release.yml`,
  `policy-size-report.yml`, `security-review-pr.yml`, and
  `quality-review-pr.yml`. The source repository owns these workflows.
- `ci/`. Plan step 3 moves the review engine into `engine/`.
- `docs/agent-policy/source-orientation.md`, `DRIFT.md`, `adopters/`,
  `policy-digests.json`, and `plan/`. These belong to the source repository.
- The test modules below read declined files. The active human approved the
  omission of each module. No adopted test changed.

| Module | Declined dependency |
|---|---|
| `test_check_compliance_tree.py` | `immutable-conflict-check.yml` |
| `test_compliance_tree_event_isolation.py` | imports `test_immutable_compliance.py` |
| `test_check_conflict_markers.py` | `immutable-conflict-check.yml`, source `README.md`, `plan/` |
| `test_ci_branch_fixtures.py` | `immutable-conflict-check.yml` |
| `test_immutable_auth_wiring.py` | `immutable-conflict-check.yml` |
| `test_immutable_compliance.py` | `immutable-conflict-check.yml` |
| `test_trusted_install_forms.py` | `immutable-conflict-check.yml` |
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

## Current drift

- `AGENTS.md` holds the policy section of `--print-adoptable` output only.
  That output also appends `docs/agent-policy/` and orientation files.
  `scripts/sync.py` appends those files again during copy generation. An
  unmodified copy of the full output exceeds the 64 KiB policy size limit.
- `docs/project-orientation.md` stays below 404 bytes. Assembly appends it to
  the policy. The template policy leaves 403 bytes below the 64 KiB limit.
- `Makefile` names this repository's prose files in `PROSE_FILES`.
- `sync-check.yml` names this repository's prose files in the prose and
  ASCII steps. The workflow omits the template-file ASCII step. This
  repository holds none of those template files.
- `.claudeignore` drops the JavaScript entries. This repository holds Python
  only.
- `hook-coverage-baseline.json` is the template file without regeneration.
  `--write-baseline` refuses to run as root. The adopting environment ran as
  root. Every file under `hooks/` is byte-identical to the template.
