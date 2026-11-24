# Data sent to the model provider

havel sends the provider three items per review chunk:

- the fenced pull request content: the diff, title, body, and file names
- `bundles/all-full.md`, the persona prompt for the privacy mode
- the trusted `regimes` option value in `TRUSTED_CONTEXT.options`

The bundle joins `AUDIT.md`, the scope profiles, every class check file,
every regime delta file, and the scope boundary. It holds no repository data beyond those policy
files. The caller workflow alone sets `regimes`. Pull request content has no
path to that value.

havel sends no secret and no personal data of its own. The persona defines
no `case_context` hook, so the model receives no repository file beyond the
diff. `tests/test_havel_persona.py` asserts the absent hook. Every eval
fixture holds synthetic data. `eval/extra_checks.py` requires each case to
state that in `fixture_notes`. A pull request diff can still contain personal
data that its author committed. The provider receives that diff as review
content.

The provider receives no GitHub token, no provider configuration file, and no
other repository secret. The review step holds `MODEL_API_KEY` only.

The engine limits apply to havel as to every persona:

- The envelope keeps pull request text in `REVIEW_TARGET` only.
  `tests/test_engine_envelope.py` covers this.
- The envelope caps the title and body. `tests/test_engine_envelope.py`
  covers this.
- Only the review step receives the provider key.
  `tests/test_review_workflow.py` covers this.

Local modes (`file`, `piece`, `wholesale`, `data-map`) run through
`engine/run_eval.py` on a workstation. A local run sends the mode bundle, the
case `declared_scope`, and one eval case to the callable that `--model-call`
names. The person running the command chooses that callable and its provider.
