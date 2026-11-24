# Provenance

These files come from `abuzucom/euler` at commit
`9488a8c5edc2045f2ab44f47bf12fac10f2994a8`. Source history stays in that
repository.

| Here | Source | Change |
|---|---|---|
| `QUALITY.md` | `QUALITY.md` | none |
| `README.md` | `README.md` | adapted to the engine: persona substance kept, the old install, CI, versioning, and contributing sections replaced with the wrapper and the root README |
| `eval/cases/quality/<case>/` | `eval/cases/<case>/` with mode `PR` | none |
| `eval/cases/file/<case>/` | `eval/cases/<case>/` with mode `File` | none |
| `eval/cases/piece/<case>/` | `eval/cases/<case>/` with mode `Piece` | none |
| `scripts/quality_checks/` | `scripts/quality_checks/` | `dependencies.py` warns on a non-object JSON manifest |
| `scripts/check_code_quality.py` | `scripts/check_code_quality.py` | none |
| `scripts/check_quality_policy.py` | `scripts/check_quality_policy.py` | none |
| `scripts/review_report.py` | `scripts/review_report.py` | none |
| `scripts/review_envelope.py` | `scripts/review_envelope.py` | none |
| `scripts/quality_reply.py` | `ci/check_review_response.py` | new name, docstring note, the engine envelope layout, and finding location checks |
| `scripts/prescan.py` | the prescan half of `ci/build_pr_case.py` | takes an extracted tree |
| `review_hooks.py` | `ci/run_review.py` and `ci/build_pr_case.py` | engine hook functions |
| `eval/extra_checks.py` | `eval/run_eval.py` | euler checks beyond the engine core |

Every case file and every script marked none matches its source byte for byte.
The mode directory comes from the `mode` field in each `expected.json`. The
`quality` directory holds the `PR` cases. The pull request review mode
carries the name `quality`.

The engine now owns chunking, the adapter, retries, and the comment. The
euler copies of those parts stay in the source repository.
