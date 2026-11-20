# agents-personas

Pull request reviewer personas on one shared review engine.

| Persona | Function | Wrapper |
|---|---|---|
| foucault | security | `.github/workflows/foucault-security-review.yml` |

- `docs/migration.md` maps old callers to the wrappers.
- `examples/` holds the always-on caller and the label caller.
- `python engine/run_eval.py --persona <name>` checks the eval cases of a
  persona.
