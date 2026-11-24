# generay

time is a four sided cube

generay audits time and date handling in code and repositories. Time
handling looks easy and fails in ways that tests rarely catch. generay lists
those failures as checks. A model reviewer applies the checks. Deterministic
scanners back the reviewer. The persona comes from `abuzucom/generay`.
`PROVENANCE.md` maps every file to its source.

## Contents

| Path | Content |
|---|---|
| `TIME.md` | Review prompt for classes C1 to C26. At most 32 KiB. |
| `SYNC.md` | Review prompt for C27, time synchronization. At most 32 KiB. |
| `docs/classes/` | Full draft of each class with facts, code patterns, fixes, and escalations. |
| `docs/problems.md` | Notes for PA-1 to PA-155, the problems and bad assumptions. |
| `docs/best-practices.md` | BP-1 to BP-4. |
| `data/ledger.json` | Maps every PA and BP to checks, and every check to its class and method. |
| `data/libraries.json` | Favored-library registry for BP-1, validated by `data/libraries.schema.json`. |
| `scripts/time_checks/` | Deterministic scanners, standard library only. |
| `eval/` | Golden corpus, split by mode. |

## How a check works

Each check has an ID such as `C7.1` and a method tag.

- `heuristic`: a scanner finds candidates.
- `both`: a scanner finds candidates and the reviewer looks for more.
- `llm`: the reviewer alone.

The engine runs the scanners as a prescan. The reviewer confirms or
dismisses every candidate. No scanner hit blocks on its own.

## Modes

| Engine mode | Prompt | Runs | Final line |
|---|---|---|---|
| `time` | `TIME.md` and `SYNC.md` | pull request review, the default | `VERDICT: APPROVE`, `BLOCK`, or `NEEDS-HUMAN` |
| `sync` | `SYNC.md` | local | the risk final line of the mode, after the `SYNC.md` status line |
| `file` | `TIME.md` and `SYNC.md` | local | `RISK: CRITICAL` to `NONE-FOUND` |
| `piece` | `TIME.md` and `SYNC.md` | local | `RISK (partial): <level>` |
| `wholesale` | `TIME.md` and `SYNC.md` | local | `RISK: CRITICAL` to `NONE-FOUND` |
| `contract` | `TIME.md` and `SYNC.md` | local | `CONTRACT: COMPLETE`, `GAPS`, or `NEEDS-HUMAN` |

Every report ends with a `VERDICT_JSON` line. `TIME.md` defines the schema.

## Running a review

`.github/workflows/generay-time-review.yml` wraps the engine workflow. The
check run carries the name `generay / time`. The `exclude_paths` input lists
whitespace-separated globs that the prescan skips. The root
[`README.md`](../../README.md) describes the review flow and the caller
patterns. [`docs/migration.md`](../../docs/migration.md) maps the old
generay workflow inputs.

This repository reviews its own pull requests with generay only under the
`generay-scan-requested` label, through
`.github/workflows/generay-time-review-pr.yml`.

## Adding content

New problems start at PA-156. The steps:

1. Add the note to `docs/problems.md`.
2. Merge it into a class under `docs/classes/`.
3. Add its checks to `TIME.md` or `SYNC.md`.
4. Record it in `data/ledger.json`.

`scripts/check_ledger_coverage.py` fails when these disagree. A new or
changed check ships with an eval case.

## Verifying changes

- `python engine/run_eval.py --persona generay` checks the eval case
  structure. [`eval/README.md`](eval/README.md) shows a live run.
- `python reviewers/generay/scripts/check_time_handling.py all src/` runs the
  scanners on a tree.
- `python reviewers/generay/scripts/check_doc_policy.py
  reviewers/generay/TIME.md` checks a review prompt.
- `python reviewers/generay/scripts/check_ledger_coverage.py --root
  reviewers/generay` checks that the ledger, the class drafts, and the
  prompts agree.
- `python reviewers/generay/scripts/validate_registry.py --schema
  reviewers/generay/data/libraries.schema.json --registry
  reviewers/generay/data/libraries.json` checks the library registry.
