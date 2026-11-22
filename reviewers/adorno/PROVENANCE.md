# Provenance

These files come from `abuzucom/adorno` at commit
`97a2c84e0aad25f70f106fe6ca668edbf43c8501`. Source history stays in that
repository.

| Here | Source | Change |
|---|---|---|
| `AUDIT.md` | `AUDIT.md` | none |
| `docs/checks/` | `docs/checks/` | none |
| `bundles.json` | `bundles.json` | none |
| `bundles/ui-full.md` | `bundles/ui-full.md` | none |
| `scripts/build_bundle.py` | `scripts/build_bundle.py` | temp file in a context manager, two type annotations, ruff format |
| `eval/cases/ui/<case>/` | `eval/cases/<case>/` with mode `PR` | none |
| `eval/cases/file/<case>/` | `eval/cases/<case>/` with mode `File` | none |
| `eval/cases/piece/<case>/` | `eval/cases/<case>/` with mode `Piece` | none |
| `eval/cases/wholesale/<case>/` | `eval/cases/<case>/` with mode `Wholesale` | none |
| `eval/cases/design-spec/<case>/` | `eval/cases/<case>/` with mode `Design-spec` | none |
| `eval/extra_checks.py` | `eval/run_eval.py` and `tests/test_eval_corpus.py` | adorno checks beyond the engine core |

Every file marked none matches its source byte for byte. The mode directory
comes from the `mode` field in each `expected.json`. The `ui` directory holds
the `PR` cases. The pull request review mode carries the name `ui`.

Every mode loads `bundles/ui-full.md`. The bundle joins `AUDIT.md` and every
`docs/checks/` file. `tests/test_adorno_bundles.py` rebuilds the bundle from
`bundles.json` and requires a byte-for-byte match.
`tests/test_adorno_build_bundle.py` covers the builder. The two test files
come from `tests/test_bundles.py` and `tests/test_build_bundle.py`. Each
file points `REPO_ROOT` at this directory and takes the ruff format layout.

`engine/run_eval.py` replaces the standalone `eval/run_eval.py`. The engine
grades the verdict line and the `VERDICT_JSON` companion. The engine joins
the case input files in name order. The adorno runner joined the files in a fixed
input-name order. `tests/test_audit_structure.py`,
`tests/test_eval_corpus.py`, and `tests/test_run_eval.py` load that runner.
The three tests stay in the source repository. `eval/extra_checks.py` keeps the corpus
rules those tests enforced.
