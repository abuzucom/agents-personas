# Provenance

These files come from `abuzucom/generay` at commit
`309d425ab1cb82819a7ec85d45a8cfd754f43a9d`. Source history stays in that
repository.

| Here | Source | Change |
|---|---|---|
| `TIME.md` | `TIME.md` | none |
| `SYNC.md` | `SYNC.md` | none |
| `data/` | `data/` | none |
| `docs/classes/` | `docs/classes/` | none |
| `docs/problems.md` | `docs/problems.md` | none |
| `docs/best-practices.md` | `docs/best-practices.md` | none |
| `eval/cases/time/<case>/` | `eval/cases/<case>/` with mode `PR` | none |
| `eval/cases/file/<case>/` | `eval/cases/<case>/` with mode `File` | none |
| `eval/cases/piece/<case>/` | `eval/cases/<case>/` with mode `Piece` | none |
| `eval/cases/contract/<case>/` | `eval/cases/<case>/` with mode `Contract` | none |
| `scripts/time_checks/` | `scripts/time_checks/` | none |
| `scripts/check_time_handling.py` | `scripts/check_time_handling.py` | none |
| `scripts/check_doc_policy.py` | `scripts/check_doc_policy.py` | named diagnostic excerpt width |
| `scripts/check_ledger_coverage.py` | `scripts/check_ledger_coverage.py` | none |
| `scripts/validate_registry.py` | `scripts/validate_registry.py` | nesting cap and named exit status |
| `scripts/time_report.py` | `scripts/review_report.py` | new name |
| `scripts/time_envelope.py` | `scripts/review_envelope.py` | new name |
| `scripts/time_reply.py` | `ci/check_review_response.py` | new name, docstring note, `time_report` import, the engine envelope layout, and finding location checks |
| `scripts/time_prescan.py` | the prescan half of `ci/build_pr_case.py` | takes an extracted tree, and the euler added-line parser |
| `review_hooks.py` | `ci/run_review.py` and `ci/build_pr_case.py` | engine hook functions |
| `eval/extra_checks.py` | `eval/run_eval.py` | generay checks beyond the engine core |

Every case file and every script marked none matches its source byte for byte.
The mode directory comes from the `mode` field in each `expected.json`. The
`time` directory holds the `PR` cases. The pull request review mode carries
the name `time`.

euler and generay each ship a `review_report.py` and a `review_envelope.py`.
The generay copies carry `time_` names. One test process can then load both
personas without a module clash.

The generay added-line parser counted a `+++` line inside a hunk as a file
header. The euler parser tracks the hunk instead. `time_prescan.py` uses the
euler parser.

generay copied 32 files from `abuzucom/euler`. The generay
`upstream-files.json` records those files. A script above with an euler
origin keeps the generay content.

Six `File` cases stay in the source repository:

- `c11-clean-iana-zone`
- `c11-fixed-offset-tz-config`
- `c27-03-positive`
- `c27-17-clean`
- `c27-17-positive`
- `c27-23-positive`

Each holds a Terraform or Kubernetes manifest fixture. The agent policy
protects both file kinds. A protected file in this repository also changes
the verdict of the repository shell gates for workspace searches.

The engine now owns chunking, the adapter, retries, and the comment. The
generay copies of those parts stay in the source repository.
