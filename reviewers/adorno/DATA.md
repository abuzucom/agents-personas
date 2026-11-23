# Data sent to the model provider

adorno sends the provider two items per review chunk:

- the fenced pull request content: the diff, title, body, and file names
- `bundles/ui-full.md`, the persona prompt for the ui mode

The bundle joins `AUDIT.md` and the `docs/checks/` detail files. It holds no
repository data beyond those policy files.

The provider receives no GitHub token, no provider configuration file, and no
other repository secret. The review step holds `MODEL_API_KEY` only.

The engine limits apply to adorno as to every persona:

- The envelope keeps pull request text in `REVIEW_TARGET` only.
  `tests/test_engine_envelope.py` covers this.
- The envelope caps the title and body. `tests/test_engine_envelope.py`
  covers this.
- Only the review step receives the provider key.
  `tests/test_review_workflow.py` covers this.

Local modes (`file`, `piece`, `wholesale`, `design-spec`) run through
`engine/run_eval.py` on a workstation. A local run sends the bundle and one
eval case to the callable that `--model-call` names. The person running the
command chooses that callable and its provider.
