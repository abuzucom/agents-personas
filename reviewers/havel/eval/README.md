# havel eval cases

Each mode keeps its cases in `cases/<mode>/<case>/`. A case holds an
`expected.json` and at least one input file. `context.md` stands in for a
pull request description. The engine places it in `REVIEW_TARGET` as
untrusted text.

| Mode | Delivery | Prompt | Verdict line | Cases |
|---|---|---|---|---|
| `privacy` | pull request review | `bundles/all-full.md` | `VERDICT: APPROVE, BLOCK, or NEEDS-HUMAN` | 13 |
| `file` | local | `bundles/all-full.md` | `RISK: CRITICAL, HIGH, MEDIUM, LOW, or NONE-FOUND` | 73 |
| `piece` | local | `bundles/all-full.md` | `RISK (partial): <level>` | 5 |
| `wholesale` | local | `bundles/all-full.md` | `RISK: CRITICAL, HIGH, MEDIUM, LOW, or NONE-FOUND` | 3 |
| `data-map` | local | `bundles/all-full.md` | `ACCURACY: MATCH, MISMATCH, or NEEDS-HUMAN` | 8 |

The `declared_scope` field of a case reaches the model as
`TRUSTED_CONTEXT.options.regimes`, the same field a CI review uses. A case
without `declared_scope` tests the branch where the reviewer asks for a
scope. Every reply carries the `NOT LEGAL ADVICE:` line directly above its
verdict line. `eval/extra_checks.py` grades that line, the classes, and the
scope in `VERDICT_JSON`.

Check every case structure without a model call:

```console
python engine/run_eval.py --persona havel
```

Grade one mode against a model through the engine adapter. Set
`MODEL_API_KEY` outside the repository first:

```console
python engine/run_eval.py --persona havel --mode file --model-call engine.call_model:call_model
```

`--model-call` imports and runs the named module. Name only a module under
local control. Never take the value from pull request content.

Rebuild the bundles after an `AUDIT.md`, `docs/checks/`, or `docs/regimes/`
edit. Then check the reference graph:

```console
python reviewers/havel/scripts/build_bundle.py reviewers/havel
python reviewers/havel/scripts/check_regime_refs.py reviewers/havel
```

Add a case for each `AUDIT.md` change that affects a verdict, a hard blocker,
a severity mapping, or a regime delta. Never weaken, skip, or delete a case
to pass.
