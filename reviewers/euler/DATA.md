# Data sent to the model provider

euler sends the provider three items per review chunk:

- the fenced pull request content: the diff, title, body, and file names
- the prescan candidates for the files of that chunk, in `REVIEW_TARGET`
- `QUALITY.md`, the persona prompt for the quality mode

A prescan candidate holds a changed file path, a line number, a QUALITY.md
class, a checker message, and a blocking flag. A checker message can quote a
short excerpt of the changed file, such as a package name, a version spec, or
a regular expression. The same text already appears in the diff.

The provider receives no GitHub token, no provider configuration file, and no
other repository secret. The prescan runs in the build step. That step holds
no secret. The reply checks run in a child process without `MODEL_API_KEY`. Only the review step holds `MODEL_API_KEY`.

Each limit names its test:

- The envelope keeps pull request text in `REVIEW_TARGET` only.
  `tests/test_engine_envelope.py` covers this with
  `test_pull_request_fields_sit_in_review_target_only`.
- Each chunk carries only the prescan candidates of its own files.
  `tests/test_engine_review_hooks.py` covers this with
  `test_each_chunk_carries_only_its_own_items`.
- The build step holds no secret. `tests/test_review_workflow_stages.py`
  covers this with `test_build_step_holds_no_secret_and_runs_the_build_stage`.
- Only the review step receives the provider key.
  `tests/test_review_workflow.py` covers this with
  `test_model_api_key_reaches_only_the_review_step`.

Local modes (`file`, `piece`, `wholesale`) run through `engine/run_eval.py`
on a workstation. A local run sends `QUALITY.md` and one eval case to the
callable that `--model-call` names. The person running the command chooses
that callable and its provider.
