# Data sent to the model provider

foucault sends the provider two items per review chunk:

- the fenced pull request content: the diff, title, body, and file names
- `AUDIT.md`, the persona prompt for the security mode

The provider receives no GitHub token, no provider configuration file, and no
other repository secret. The review step holds `MODEL_API_KEY` only.

Each limit names its test:

- The envelope keeps pull request text in `REVIEW_TARGET` only.
  `tests/test_engine_envelope.py` covers this with
  `test_pull_request_fields_sit_in_review_target_only` and
  `test_metadata_carrying_pull_request_text_is_rejected`.
- The envelope caps the title and body. `tests/test_engine_envelope.py`
  covers this with `test_long_title_is_truncated_and_recorded` and
  `test_long_body_is_truncated_and_recorded`.
- Only the review step receives the provider key.
  `tests/test_review_workflow.py` covers this with
  `test_model_api_key_reaches_only_the_review_step`.

Local modes (`file`, `piece`, `wholesale`) run through `engine/run_eval.py`
on a workstation. A local run sends `AUDIT.md` and one eval case to the
callable that `--model-call` names. The person running the command chooses
that callable and its provider.
