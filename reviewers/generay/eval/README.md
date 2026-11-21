# generay eval cases

Each mode keeps its cases in `cases/<mode>/<case>/`. A case holds an
`expected.json` and its input files. A `time` case holds `diff.patch`. Other
cases hold an `input.<ext>` file or a named configuration file such as
`chrony.conf` or `Dockerfile`. `context.md` adds context.

| Mode | Delivery | Verdict line | Cases |
|---|---|---|---|
| `time` | pull request review | `VERDICT: APPROVE, BLOCK, or NEEDS-HUMAN` | 2 |
| `file` | local | `RISK: CRITICAL, HIGH, MEDIUM, LOW, or NONE-FOUND` | 98 |
| `piece` | local | `RISK (partial): <level>` | 1 |
| `wholesale` | local | `RISK: CRITICAL, HIGH, MEDIUM, LOW, or NONE-FOUND` | 0 |
| `contract` | local | `CONTRACT: COMPLETE, GAPS, or NEEDS-HUMAN` | 4 |

Check every case structure and the scanner output without a model call:

```console
python engine/run_eval.py --persona generay
```

The structure check also runs the time scanners on each non-PR case. The
scanners must report exactly the check IDs in `expected_prescan`.

Grade one mode against a model through the engine adapter. Set
`MODEL_API_KEY` outside the repository first:

```console
python engine/run_eval.py --persona generay --mode file --model-call engine.call_model:call_model
```

`--model-call` imports and runs the named module. Name only a module under
local control. Never take the value from pull request content.

Run the time scanners over local files:

```console
python reviewers/generay/scripts/check_time_handling.py all src/
```

Check the prompt structure, the ledger coverage, and the library registry:

```console
python reviewers/generay/scripts/check_doc_policy.py reviewers/generay/TIME.md
python reviewers/generay/scripts/check_doc_policy.py reviewers/generay/SYNC.md
python reviewers/generay/scripts/check_ledger_coverage.py --root reviewers/generay
python reviewers/generay/scripts/validate_registry.py
```

Add a case for each `TIME.md` or `SYNC.md` change that affects a verdict, a
severity, or a check. Never weaken, skip, or delete a case to pass.
