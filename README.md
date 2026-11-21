# agents-personas

Pull request reviewer personas on one shared review engine.

| Persona | Function | Wrapper |
|---|---|---|
| foucault | security | `.github/workflows/foucault-security-review.yml` |
| euler | quality | `.github/workflows/euler-quality-review.yml` |

- `docs/migration.md` maps old callers to the wrappers.
- `examples/` holds the always-on caller and the label caller.
- `python engine/run_eval.py --persona <name>` checks the eval cases of a
  persona. With `--model-call` and `--repeat N`, it sends each case N times
  and reports how often the runs agree on a verdict.
- A person adds the `eval-live` label to grade the changed personas of a
  pull request against the live model. The engine and the grader come from
  the default branch. The pull request persona reaches the run as data.
- The review workflow reuses a failing check run for the same head and
  input set. A passing result always reruns. A push, a title or body edit,
  or a changed option starts a new review.
- Persona hooks require bubblewrap at `/usr/bin/bwrap` by default. A run
  fails closed without it. On a host without bubblewrap, set
  `PERSONAS_REQUIRE_SANDBOX=0` for a local run. The hook then runs as a
  plain child after a warning.
