# foucault eval cases

Each mode keeps its cases in `cases/<mode>/<case>/`. A case holds an
`expected.json` and at least one input file. `context.md` and
`hook_context.md` add trusted context.

| Mode | Delivery | Verdict line | Cases |
|---|---|---|---|
| `security` | pull request review | `VERDICT: APPROVE, BLOCK, or NEEDS-HUMAN` | 21 |
| `file` | local | `RISK: CRITICAL, HIGH, MEDIUM, LOW, or NONE-FOUND` | 45 |
| `piece` | local | `RISK (partial): <level>` | 1 |
| `wholesale` | local | `RISK: CRITICAL, HIGH, MEDIUM, LOW, or NONE-FOUND` | 1 |

Check every case structure without a model call:

```console
python engine/run_eval.py --persona foucault
```

Grade one mode against a model through the engine adapter. Set
`MODEL_API_KEY` outside the repository first:

```console
python engine/run_eval.py --persona foucault --mode file --model-call engine.call_model:call_model
```

A pull request with the `eval-live` label runs the same live grading in CI.
The default branch supplies the engine and `extra_checks.py`.

`--model-call` imports and runs the named module. Name only a module under
local control. Never take the value from pull request content.

Add a case for each `AUDIT.md` change that affects a verdict, a hard blocker,
or a severity mapping. Never weaken, skip, or delete a case to pass.
