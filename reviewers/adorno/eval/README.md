# adorno eval cases

Each mode keeps its cases in `cases/<mode>/<case>/`. A case holds an
`expected.json` and at least one input file. `context.md` adds trusted
context.

| Mode | Delivery | Verdict line | Cases |
|---|---|---|---|
| `ui` | pull request review | `VERDICT: APPROVE, BLOCK, or NEEDS-HUMAN` | 1 |
| `file` | local | `RISK: CRITICAL, HIGH, MEDIUM, LOW, or NONE-FOUND` | 36 |
| `piece` | local | `RISK (partial): <level>` | 1 |
| `wholesale` | local | `RISK: CRITICAL, HIGH, MEDIUM, LOW, or NONE-FOUND` | 1 |
| `design-spec` | local | `CONFORMANCE: MATCH, MISMATCH, or NEEDS-HUMAN` | 2 |

Check every case structure without a model call:

```console
python engine/run_eval.py --persona adorno
```

Grade one mode against a model through the engine adapter. Set
`MODEL_API_KEY` outside the repository first:

```console
python engine/run_eval.py --persona adorno --mode file --model-call engine.call_model:call_model
```

`--model-call` imports and runs the named module. Name only a module under
local control. Never take the value from pull request content.

Rebuild the bundle after an `AUDIT.md` or `docs/checks/` edit:

```console
python reviewers/adorno/scripts/build_bundle.py reviewers/adorno
```

Add a case for each `AUDIT.md` change that affects a verdict, a hard blocker,
or a severity mapping. Never weaken, skip, or delete a case to pass.
