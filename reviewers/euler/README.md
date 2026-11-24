# euler

euler reviews code quality and conventions in LLM-assisted software
development. It applies explicit rules to pull requests, files, fragments, and
whole codebases. It produces findings, evidence, and a machine-readable
verdict. The persona comes from `abuzucom/euler`. `PROVENANCE.md` maps every
file to its source.

## Relationship to foucault

foucault reviews security. euler reviews code quality and conventions. The
two run side by side. `QUALITY.md` section 9 routes security findings to
foucault. The dependency classes overlap foucault by design.

## Policy

[`QUALITY.md`](QUALITY.md) is the review contract. The engine sends it as the
system prompt. It defines these parts:

- **Four review modes.** PR, File, Piece, and Wholesale.
- **Classes.** Correctness (Q), maintainability (M), conventions (C), and
  dependencies (D).
- **Tiers.** Blocking, Escalate, Graded, and Advisory.
- **Verdicts.** `APPROVE`, `BLOCK`, or `NEEDS-HUMAN` for a pull request. A
  `RISK` summary for the other modes. A `VERDICT_JSON` line in every mode.

The rules derive from a reviewed subset of the `abuzucom/vibe-check` list plus
approved additions.

| Tier | Effect |
|---|---|
| Blocking | Any finding gives BLOCK. |
| Escalate | Any finding gives NEEDS-HUMAN. |
| Graded | The model rates each finding. HIGH gives BLOCK. |
| Advisory | Always LOW. The verdict stays unaffected. |

| ID | Class | Tier |
|---|---|---|
| Q1 | Contradictory or impossible logic | Blocking |
| Q2 | Unintended global or request-state caching | Graded |
| Q3 | Catastrophic regex backtracking | Graded +script |
| Q4 | Unchecked divisor | Blocking |
| Q5 | Unreachable dead code | Graded +script |
| Q6 | Obvious performance drains | Graded |
| Q7 | Single responsibility | Advisory |
| Q8 | Mutation during iteration | Graded +script |
| Q9 | Recursion without a depth limit | Graded +script |
| Q10 | Concurrency | Graded |
| Q11 | Resource leaks | Blocking +script |
| Q12 | Hallucinated APIs | Blocking |
| Q13 | Language traps | Graded +script |
| Q14 | Missing idempotency | Graded |
| M1 | Empty or swallowing catch blocks | Blocking +script |
| M2 | Non-descriptive names | Advisory |
| M3 | Function purpose not self-evident | Advisory |
| M4 | Large undocumented anonymous functions | Advisory |
| M5 | Needlessly verbose code | Advisory |
| M6 | Broken public API contract | Escalate |
| M7 | Deep nesting | Advisory |
| M8 | Long functions | Advisory |
| M9 | Break in nested loops | Advisory |
| M10 | Duplication | Blocking |
| M11 | Magic numbers | Blocking |
| M12 | Incomplete work | Blocking +script |
| M13 | Suppressed checks | Blocking +script |
| M14 | Comment drift | Graded |
| M15 | Over-engineering | Graded |
| M16 | Broad catch or uninformative error | Graded +script |
| M17 | Debug leftovers | Graded +script |
| M18 | Hardcoded environment values | Graded +script |
| C1 | Repository convention deviation | Graded |
| C2 | Test integrity | Escalate |
| C3 | Untested changes | Graded +script |
| D1 | Unpinned versions | Escalate +script |
| D2 | Lockfile drift | Escalate +script |
| D3 | Unjustified new dependency | Escalate |
| D4 | Redundant or overlapping dependencies | Graded |
| D5 | Unused or undeclared dependencies | Graded +script |
| D6 | Deprecated or stale dependencies | Graded |

`+script` marks a class with a deterministic heuristic checker in
`scripts/check_code_quality.py`. The engine runs the checkers as a prescan.
The model confirms or dismisses each candidate.

## Modes

| Engine mode | Source mode | Runs | Final line |
|---|---|---|---|
| `quality` | PR | pull request review, the default | `VERDICT: APPROVE`, `BLOCK`, or `NEEDS-HUMAN` |
| `file` | File | local | `RISK: HIGH` to `NONE-FOUND` |
| `piece` | Piece | local | `RISK (partial): <level>` or `NEEDS-HUMAN` |
| `wholesale` | Wholesale | local | `RISK: HIGH` to `NONE-FOUND` |

## Running a review

`.github/workflows/euler-quality-review.yml` wraps the engine workflow. The
check run carries the name `euler / quality`. The `exclude_paths` input lists
whitespace-separated globs that the prescan skips. The root
[`README.md`](../../README.md) describes the review flow and the caller
patterns. [`docs/migration.md`](../../docs/migration.md) maps the inputs of
the old `quality-review.yml`.

This repository reviews its own pull requests with euler through
`.github/workflows/euler-quality-review-pr.yml`.

## Verifying changes

- `python engine/run_eval.py --persona euler` checks the eval case
  structure. [`eval/README.md`](eval/README.md) shows a live run.
- `python reviewers/euler/scripts/check_code_quality.py all src/` runs the
  deterministic checkers on a tree.
- `python reviewers/euler/scripts/check_quality_policy.py
  reviewers/euler/QUALITY.md` checks the class IDs and tiers, the verdict
  tokens, unique headings, ASCII text, LF line endings, prose line length,
  prose dashes, and the 32 KiB size cap.
- A change to a class, a tier, a hard blocker, or the `VERDICT_JSON` schema
  ships with a new or updated eval case.
