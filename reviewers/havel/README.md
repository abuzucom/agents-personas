# havel

havel audits code for data-privacy compliance. It reviews a pull request, a
single file, a code fragment, a whole codebase, or a declared data map paired
with its implementation. The persona comes from `abuzucom/havel`.
`PROVENANCE.md` maps every file to its source.

**Not legal advice.** havel distills public statutory text into engineering
checklists. It carries no warranty. No output establishes compliance. Every
finding is an input to legal review. It never substitutes for that review.
Read
[`docs/legal-disclaimer.md`](docs/legal-disclaimer.md) before relying on any
result.

## Regime coverage

havel covers 15 regimes across 29 failure-mode classes.

| Territory | Regimes |
|---|---|
| European Union | GDPR, ePrivacy, eIDAS 2.0 privacy provisions |
| Germany | TTDSG and UWG section 7, as `de-national` |
| United Kingdom | UK GDPR, PECR |
| United States | CCPA, TDPSA, VCDPA, CPA, CTDPA, UCPA |
| Canada | PIPEDA, Quebec Law 25 |
| Brazil | LGPD |

Sectoral American law stays out of scope. That exclusion covers HIPAA, GLBA,
COPPA, and FERPA.

## Regime scope

The agent never decides which regimes apply. Applicability turns on facts
absent from code. The caller declares the scope with the `regimes` input.
Take the value from counsel's answer, not from the look of the codebase.

- `regimes` takes profile names or slugs, comma separated.
  [`docs/regimes/scope-profiles.md`](docs/regimes/scope-profiles.md) holds
  the authoritative expansion. `eu` expands to `gdpr`, `eprivacy`, and
  `eidas`, for example.
- The value reaches the model in `TRUSTED_CONTEXT.options.regimes`. A scope
  line inside the pull request text carries no authority.
- `review_hooks.py` refuses an unknown name or a blank list entry before the
  review starts.
- An empty value, `baseline`, or `undeclared` reviews the baseline classes
  alone. The check summary and the comment then carry a fixed note. The note
  says that regime-specific issues may exist that the run did not check. The
  report also names the unchecked obligations on its `Unseen:` line.

## What this checks and what it does not

[`docs/scope-boundary.md`](docs/scope-boundary.md) lists every exclusion and
names where it belongs.

- Cryptography, certificate handling, key custody, signature formats, and
  application security route to foucault. Class 2.20 is the seam. It covers
  only the controls a privacy regime names as an obligation. foucault owns
  whether a control holds against an attacker.
- Employment-context processing stays out of scope. The data subject havel
  reviews is a user or a customer.

## Modes

Every mode sends `bundles/all-full.md`, the full tier with every regime. The
`regimes` input, not the bundle, sets the scope.

| Engine mode | Source mode | Runs | Final line |
|---|---|---|---|
| `privacy` | PR | pull request review, the default | `VERDICT: APPROVE`, `BLOCK`, or `NEEDS-HUMAN` |
| `file` | File | local | `RISK: CRITICAL` to `NONE-FOUND` |
| `piece` | Piece | local | `RISK (partial): <level>` or `NEEDS-HUMAN` |
| `wholesale` | Wholesale | local | `RISK: CRITICAL` to `NONE-FOUND` |
| `data-map` | Data-map | local | `ACCURACY: MATCH`, `MISMATCH`, or `NEEDS-HUMAN` |

Every report carries the `NOT LEGAL ADVICE:` line directly above its verdict
line. `review_hooks.py` rejects a review reply without it.

## Running a review

`.github/workflows/havel-privacy-review.yml` wraps the engine workflow. The
check run carries the name `havel / privacy`. `MODEL_API_KEY` stays optional.
The root [`README.md`](../../README.md) describes the review flow and the
caller patterns. [`docs/migration.md`](../../docs/migration.md) maps the
inputs of the old `privacy-review.yml`.

This repository reviews its own pull requests with havel only under the
`havel-scan-requested` label, with the `baseline` scope, through
`.github/workflows/havel-privacy-review-pr.yml`.

## Pasting a bundle

A chat review needs no tooling. Paste a generated bundle, then the code under
review. The chosen bundle declares the scope. Each scope ships two tiers. The
standard tier carries the hub, the scope regime deltas, and the scope
boundary. The full tier adds every class reference file.

| Bundle | Standard | Full | Regimes applied |
|---|---|---|---|
| `baseline` | 33 KB | 120 KB | none |
| `eu` | 47 KB | 135 KB | gdpr, eprivacy, eidas |
| `de` | 50 KB | 137 KB | gdpr, eprivacy, eidas, de-national |
| `uk` | 37 KB | 125 KB | uk-gdpr, pecr |
| `us` | 47 KB | 134 KB | ccpa, tdpsa, vcdpa, cpa, ctdpa, ucpa |
| `canada` | 37 KB | 124 KB | pipeda, law25 |
| `brazil` | 35 KB | 123 KB | lgpd |
| `all` | 74 KB | 161 KB | every regime |

`scripts/build_bundle.py` generates the bundles. Edit `AUDIT.md`, a file
under `docs/checks/`, or a file under `docs/regimes/`. Then run
`python reviewers/havel/scripts/build_bundle.py reviewers/havel`.

## Files

| Path | Purpose |
|---|---|
| `AUDIT.md` | The hub. Sections 0 through 9 plus the regime scope table. |
| `docs/checks/2.N.md` | Per-class mechanism, thresholds, and investigation. |
| `docs/regimes/<slug>.md` | Per-regime deltas alone. |
| `docs/regimes/scope-profiles.md` | The authoritative profile expansion. |
| `bundles/` | Generated prompts and paste-ready documents. |
| `eval/` | The golden corpus, split by mode. |

## Customization

- Name the languages, frameworks, and stores in use. Fixes then stay
  concrete.
- Record scope boundaries such as monorepo paths and generated files.
- Add a waiver rule and state who may use it.

## Verifying changes

- `python engine/run_eval.py --persona havel` checks the eval case
  structure. [`eval/README.md`](eval/README.md) shows a live run.
- `python reviewers/havel/scripts/build_bundle.py reviewers/havel --check`
  fails when a committed bundle differs from its sources.
- `python reviewers/havel/scripts/check_regime_refs.py reviewers/havel`
  checks the regime references and the scope profiles.
- A pinned commit freezes the profile expansion. A new statute therefore
  never widens an existing audit without an explicit pin change.
