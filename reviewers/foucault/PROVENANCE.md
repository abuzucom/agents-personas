# Provenance

These files come from `abuzucom/foucault` at commit
`9ec9681131841bae8bd80bdffdfcb673b36a6289`. Source history stays in that
repository.

| Here | Source | Change |
|---|---|---|
| `AUDIT.md` | `AUDIT.md` | none |
| `README.md` | `README.md` | adapted to the engine: persona substance kept, the old install, CI, versioning, and contributing sections replaced with the wrapper and the root README |
| `eval/cases/security/<case>/` | `eval/cases/<case>/` with mode `PR` | none |
| `eval/cases/file/<case>/` | `eval/cases/<case>/` with mode `File` | none |
| `eval/cases/piece/<case>/` | `eval/cases/<case>/` with mode `Piece` | none |
| `eval/cases/wholesale/<case>/` | `eval/cases/<case>/` with mode `Wholesale` | none |
| `eval/extra_checks.py` | `eval/run_eval.py` | foucault checks beyond the engine core |
| `scripts/check_audit_policy.py` | `scripts/check_audit_policy.py` | default path and recovery message |

Every case file matches its source byte for byte. The mode directory comes
from the `mode` field in each `expected.json`. The `security` directory holds
the `PR` cases. The pull request review mode carries the name `security`.

`engine/run_eval.py` replaces the standalone `eval/run_eval.py`. The engine
grades the verdict line, `REVIEW STATUS`, and the `VERDICT_JSON` companion.
`eval/extra_checks.py` adds the exact `VERDICT_JSON` keys, the report
contract, and the `omit_provenance` input.
