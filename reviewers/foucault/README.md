# foucault

foucault reviews security in LLM-assisted software development. It applies
explicit rules to pull requests, files, code fragments, and whole codebases.
It produces findings, evidence requirements, and a machine-readable verdict.
The persona comes from `abuzucom/foucault`. `PROVENANCE.md` maps every file
to its source.

## Design position

foucault uses operational controls. Each control names a condition, an
action, the required evidence, and a result. The engine, the eval corpus, and
the persona checker supply the enforcement surface.

foucault makes no personal appeal to the model. It uses no dramatic authority
claim to override the policy. It grants no unrestricted authority with a later
prohibition as the only limit. A security boundary must hold across the whole
execution path.

## Policy

[`AUDIT.md`](AUDIT.md) is the review contract. The engine sends it as the
system prompt. It separates review evidence from trusted context. It defines:

- **Four review modes.** PR reviews a diff and gates a merge. File reviews one
  file on demand. Piece reviews a fragment with unseen context. Wholesale
  reviews a whole codebase. The failure-mode classes apply in every mode.
- **Review principles.** Attacker-path analysis, exploitability first,
  explicit context boundaries, and evidence for every finding.
- **15 failure-mode classes.** Examples include hallucinated dependencies,
  missing authorization, injection, insecure defaults, and weak cryptography.
- **A 9-step workflow.** Applicability, context, dependencies, entry points,
  data flow, failure paths, configuration, consistency, and report. Each step
  states its per-mode substitution.
- **Hard blockers.** These findings give BLOCK with no discretion.
- **Verdicts by mode.** Section 6 lists the verdict line of each mode. Every
  mode also ends with a `VERDICT_JSON` line.
- **False-positive rules.** What not to flag, and the ban on inflated
  severity.

| Section | Purpose |
|---|---|
| 0 | Review modes |
| 1 | Review principles |
| 2 | Failure modes in AI-assisted code (2.1 to 2.15) |
| 3 | Review workflow |
| 4 | Verification tests |
| 5 | Hard blockers |
| 6 | Reporting format |
| 7 | Review prohibitions, including prompt-injection defense |
| 8 | False-positive exclusions |
| 9 | Zero-finding review |

## Modes

| Engine mode | Source mode | Runs | Final line |
|---|---|---|---|
| `security` | PR | pull request review, the default | `VERDICT: APPROVE`, `BLOCK`, or `NEEDS-HUMAN` |
| `file` | File | local | `RISK: CRITICAL` to `NONE-FOUND` |
| `piece` | Piece | local | `RISK (partial): <level>` or `NEEDS-HUMAN` |
| `wholesale` | Wholesale | local | `RISK: CRITICAL` to `NONE-FOUND` |

## Running a review

`.github/workflows/foucault-security-review.yml` wraps the engine workflow.
The check run carries the name `foucault / security`. The root
[`README.md`](../../README.md) describes the review flow and the caller
patterns. [`docs/migration.md`](../../docs/migration.md) maps the inputs of
the old `security-review.yml`.

This repository reviews its own pull requests with foucault through
`.github/workflows/foucault-security-review-pr.yml`.

## Customization

The policy is stack-agnostic. Deployment details improve finding accuracy:

- languages, frameworks, the ORM, the authentication middleware, and the
  secret manager;
- scope boundaries such as monorepo paths and vendored or generated files;
- a waiver rule for findings and the people who may apply it.

## Agent governance and review

foucault and `abuzucom/agents` act at different control points.

- `abuzucom/agents` governs implementation time. It defines repository
  rules, command gates, file gates, and authorization boundaries for coding
  agents.
- foucault evaluates a proposed or existing artifact. It produces findings,
  evidence requirements, severity, and a verdict.

Both can cover the same vulnerability class. `AGENTS.md` can prevent unsafe
command construction during implementation. `AUDIT.md` can find it in a
review target. Neither control replaces the other. A missing or ambiguous
control escalates to `NEEDS-HUMAN`. It never grants an exception.

## Verifying changes

- `python engine/run_eval.py --persona foucault` checks the eval case
  structure. [`eval/README.md`](eval/README.md) shows a live run.
- `python reviewers/foucault/scripts/check_audit_policy.py
  reviewers/foucault/AUDIT.md` checks the
  required sections, verdict tokens, injection controls, ASCII text, LF line
  endings, and the size limit of `AUDIT.md`.
- A change to `AUDIT.md` that affects a verdict, a hard blocker, or a
  severity mapping ships with a new or updated eval case.
