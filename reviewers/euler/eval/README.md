# euler eval cases

Each mode keeps its cases in `cases/<mode>/<case>/`. A case holds an
`expected.json` and its input files. A `quality` case holds `diff.patch`.
Other cases hold an `input.<ext>` file. `context.md` adds the pull request
context.

| Mode | Delivery | Verdict line | Cases |
|---|---|---|---|
| `quality` | pull request review | `VERDICT: APPROVE, BLOCK, or NEEDS-HUMAN` | 30 |
| `file` | local | `RISK: HIGH, MEDIUM, LOW, or NONE-FOUND` | 10 |
| `piece` | local | `RISK (partial): <level>` | 1 |
| `wholesale` | local | `RISK: HIGH, MEDIUM, LOW, or NONE-FOUND` | 0 |

Check every case structure without a model call:

```console
python engine/run_eval.py --persona euler
```

Grade one mode against a model through the engine adapter. Set
`MODEL_API_KEY` outside the repository first:

```console
python engine/run_eval.py --persona euler --mode file --model-call engine.call_model:call_model
```

`--model-call` imports and runs the named module. Name only a module under
local control. Never take the value from pull request content.

Run the deterministic prescan over local files:

```console
python reviewers/euler/scripts/check_code_quality.py all src/
```

Check the prompt structure, class tiers, encoding, width, and size:

```console
python reviewers/euler/scripts/check_quality_policy.py reviewers/euler/QUALITY.md
```
