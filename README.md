# agents-personas

Pull request reviewer personas on one shared review engine.

| Persona | Function | Wrapper |
|---|---|---|
| foucault | security | `.github/workflows/foucault-security-review.yml` |
| euler | quality | `.github/workflows/euler-quality-review.yml` |

- `docs/migration.md` maps old callers to the wrappers.
- `examples/` holds the always-on caller and the label caller.
- `python engine/run_eval.py --persona <name>` checks the eval cases of a
  persona.
- Persona hooks require bubblewrap at `/usr/bin/bwrap` by default. A run
  fails closed without it. On a host without bubblewrap, set
  `PERSONAS_REQUIRE_SANDBOX=0` for a local run. The hook then runs as a
  plain child after a warning.
