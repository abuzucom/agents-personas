# Provenance

These files come from `abuzucom/havel` at commit
`58571431d634a7c1da88128733c57176b9208e7c`. Source history stays in that
repository.

| Here | Source | Change |
|---|---|---|
| `AUDIT.md` | `AUDIT.md` | step 0b scope source, section 6 disclaimer position |
| `docs/checks/` | `docs/checks/` | none |
| `docs/regimes/` | `docs/regimes/` | none |
| `docs/scope-boundary.md` | `docs/scope-boundary.md` | none |
| `docs/legal-disclaimer.md` | `docs/legal-disclaimer.md` | none |
| `bundles.json` | `bundles.json` | none |
| `bundles/*.md` | `bundles/*.md` | rebuilt from the edited `AUDIT.md` |
| `scripts/build_bundle.py` | `scripts/build_bundle.py` | temp file in a context manager, two type annotations, ruff format, `output_path` refuses a symlinked or escaping `bundles/` |
| `scripts/check_regime_refs.py` | `scripts/check_regime_refs.py` | ruff format, two dict annotations, a named sort key for mypy |
| `eval/cases/privacy/<case>/` | `eval/cases/<case>/` with mode `PR` | none |
| `eval/cases/file/<case>/` | `eval/cases/<case>/` with mode `File` | none |
| `eval/cases/piece/<case>/` | `eval/cases/<case>/` with mode `Piece` | none |
| `eval/cases/wholesale/<case>/` | `eval/cases/<case>/` with mode `Wholesale` | none |
| `eval/cases/data-map/<case>/` | `eval/cases/<case>/` with mode `Data-map` | none |
| `eval/extra_checks.py` | `eval/run_eval.py` | havel checks beyond the engine core |

Two source cases stay in the source repository: `cross-border-file` and
`security-defers-to-foucault-file`. Each holds an `input.tf` fixture. The
repository gates treat Terraform source as protected infrastructure content
under AGENTS.md Rule 15. A tracked `.tf` file makes every recursive search
of the repository deny. The other 102 cases moved.

Every file marked none matches its source byte for byte. The mode directory
comes from the `mode` field in each `expected.json`. The `privacy` directory
holds the `PR` cases. The pull request review mode carries the name
`privacy`.

## AUDIT.md edits

Two edits fit the hub to the shared engine. Every bundle carries both after
the rebuild.

- Step 0b names `TRUSTED_CONTEXT.options.regimes` as the workflow input. The
  source workflow sent a `DECLARED_SCOPE:` line ahead of an
  `UNTRUSTED CONTENT` frame. The engine sends the caller value in
  `TRUSTED_CONTEXT` and the pull request text in `REVIEW_TARGET`. Every
  bundle header also carries a `DECLARED_SCOPE:` line. The edit gives the
  trusted option precedence over that header line. The review mode sends
  `bundles/all.md`, whose header declares `all`. Without the precedence rule
  the header would widen the declared scope to every regime.
- Section 6 places the `NOT LEGAL ADVICE:` line directly above the verdict
  line. The source placed it after `VERDICT_JSON`. The engine requires
  `VERDICT_JSON` as the final report line. `review_hooks.py` and
  `eval/extra_checks.py` require the line in the new position.

The `planted-scope-in-description-pr` notes describe the source frame. The
case still holds. A `DECLARED_SCOPE:` line inside `REVIEW_TARGET` carries no
authority under the edited step 0b.

## Mode prompts

The `privacy`, `file`, `piece`, and `data-map` modes send `bundles/all.md`,
the standard tier with every regime. The `wholesale` mode sends
`bundles/all-full.md`. The source README assigns the standard tier to a pull
request review and the full tier to a whole-codebase audit. The source
workflow sent `AUDIT.md` alone. That hub points at the scope profiles, the
regime deltas, and the scope boundary. None of those files reached the model.
`tests/test_havel_persona.py` requires every one of them in the review
prompt.

## Tests and runner

`tests/test_havel_bundles.py`, `tests/test_havel_build_bundle.py`,
`tests/test_havel_check_regime_refs.py`, and
`tests/test_havel_reference_graph.py` come from `tests/test_bundles.py`,
`tests/test_build_bundle.py`, `tests/test_check_regime_refs.py`, and
`tests/test_reference_graph.py`. Each file points `REPO_ROOT` at this
directory and takes the ruff format layout.

`engine/run_eval.py` replaces the standalone `eval/run_eval.py`. The engine
grades the verdict line and the `VERDICT_JSON` companion.
`eval/extra_checks.py` keeps the scope rules, the class tokens, and the
disclaimer check of the source runner. It places `declared_scope` in
`TRUSTED_CONTEXT.options.regimes`. `tests/test_audit_structure.py`,
`tests/test_eval_corpus.py`, and `tests/test_response_parsing.py` load the
source runner. The three tests stay in the source repository.
