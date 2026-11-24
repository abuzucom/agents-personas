# adorno

adorno audits interfaces for UI, UX, and accessibility defects. It targets the
barriers common in AI-assisted coding. Such an interface renders and demos
fine. A keyboard user, a screen-reader user, a low-vision user, or a
motion-sensitive user still cannot complete a task with it. The persona comes
from `abuzucom/adorno`. `PROVENANCE.md` maps every file to its source.

## Policy

[`AUDIT.md`](AUDIT.md) is the review contract. It defines:

- **Five review modes.** PR reviews a diff and gates a merge. File reviews
  one component on demand. Piece reviews a fragment with unseen context.
  Wholesale reviews a whole interface. Design-spec audits a design source
  against its implementation. The failure-mode classes apply in every mode.
- **Operating principles.** Assume AI-generated output. Think like an
  excluded user. Rank by how completely a barrier excludes a user. State what
  stays out of view.
- **23 failure-mode classes.** Section 2 runs from non-semantic elements and
  keyboard focus to locale formatting and dark-mode integrity.
- **An 8-step workflow.** Context, design source, structure and semantics,
  sensory and input, dynamic behavior, media and intent, consistency, and
  report. Each step states its per-mode substitution.
- **Hard blockers.** A short list of catastrophic exclusions that give BLOCK
  with no discretion.
- **Verdicts by mode.** Every mode also ends with a `VERDICT_JSON` line.
- **False-positive rules.** What not to flag, and the ban on inflated
  severity.

Each class entry in section 2 is a summary. Its thresholds, mechanism, and
investigation steps live in `docs/checks/2.N.md`.

| Section | Purpose |
|---|---|
| 0 | Review modes |
| 1 | Operating principles |
| 2 | Failure-mode classes (2.1 to 2.23) |
| 3 | Review workflow |
| 4 | Verifying the verifier |
| 5 | Hard blockers |
| 6 | Reporting format |
| 7 | Prohibitions, including prompt-injection defense |
| 8 | False positives |
| 9 | Zero-findings protocol |

## Bundle

Every mode sends `bundles/ui-full.md` as the system prompt. Each `AUDIT.md`
class entry ends with a `Detail: docs/checks/2.N.md` pointer. A model call
cannot follow a repository path. The bundle concatenates `AUDIT.md` with all
23 check files. Each pointer then resolves to a section further down the same
prompt.

| File | Size | Use |
|---|---|---|
| `bundles/ui-full.md` | 109,646 bytes | The prompt for every mode and for a pasted chat review. |
| `AUDIT.md` | 22,031 bytes | A tool that reads `docs/checks/` from the repository itself. |

`scripts/build_bundle.py` generates `bundles/ui-full.md`. Edit `AUDIT.md` or
a file under `docs/checks/`. Then run
`python reviewers/adorno/scripts/build_bundle.py reviewers/adorno`.
`bundles.json` declares the bundle sources. A test rebuilds the bundle and
fails when the committed copy no longer matches its sources.

## Modes

| Engine mode | Source mode | Runs | Final line |
|---|---|---|---|
| `ui` | PR | pull request review, the default | `VERDICT: APPROVE`, `BLOCK`, or `NEEDS-HUMAN` |
| `file` | File | local | `RISK: CRITICAL` to `NONE-FOUND` |
| `piece` | Piece | local | `RISK (partial): <level>` or `NEEDS-HUMAN` |
| `wholesale` | Wholesale | local | `RISK: CRITICAL` to `NONE-FOUND` |
| `design-spec` | Design-spec | local | `CONFORMANCE: MATCH`, `MISMATCH`, or `NEEDS-HUMAN` |

## Running a review

`.github/workflows/adorno-ui-review.yml` wraps the engine workflow. The check
run carries the name `adorno / ui`. `MODEL_API_KEY` stays optional. The root
[`README.md`](../../README.md) describes the review flow and the caller
patterns. [`docs/migration.md`](../../docs/migration.md) maps the inputs of
the old `ui-review.yml`.

This repository reviews its own pull requests with adorno only under the
`adorno-scan-requested` label, through
`.github/workflows/adorno-ui-review-pr.yml`.

## Customization

The policy is stack-agnostic. Deployment details make the fixes concrete:

- the frameworks, the component library, the design-token format, and the
  assistive-technology target set;
- scope boundaries such as monorepo paths and vendored or generated files;
- a waiver rule for findings and the people who may apply it.

## Agent governance and review

adorno and `abuzucom/agents` defend against AI-assisted coding failures at
different times.

- `abuzucom/agents` guards work in progress. Its hooks block a violation
  before a commit or a tool call completes.
- adorno reviews a pull request or a piece of work after the interface
  exists.

## Verifying changes

- `python engine/run_eval.py --persona adorno` checks the eval case
  structure. [`eval/README.md`](eval/README.md) shows a live run.
- `python reviewers/adorno/scripts/build_bundle.py reviewers/adorno --check`
  fails when a committed bundle differs from its sources.
- A change to `AUDIT.md` that affects a verdict, a hard blocker, or a
  severity mapping ships with a new or updated eval case.
