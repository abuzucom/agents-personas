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
no secret. Every euler hook runs in a child process with an allowlisted
environment that holds no credential. The child starts in an empty
temporary home. Bubblewrap runs each hook without network access. A run
without a trusted `/usr/bin/bwrap` fails closed unless
`PERSONAS_REQUIRE_SANDBOX=0` allows a local fallback. The hook sees only
`/usr`, five runtime files in `/etc`, the Python installation, the engine,
the persona, and the head tree copy (decision 33). On Linux, the engine
process is non-dumpable. A hook cannot read the key from `/proc`. Only the
review step holds `MODEL_API_KEY`.

Each limit names its test:

- The envelope keeps pull request text in `REVIEW_TARGET` only.
  `tests/test_engine_envelope.py` covers this with
  `test_pr_fields_stay_in_target`.
- Each chunk carries only the prescan candidates of its own files.
  `tests/test_engine_review_hooks.py` covers this with
  `test_chunk_carries_own_items`.
- The build step holds no secret. `tests/test_review_workflow_stages.py`
  covers this with `test_build_step_lacks_secret`.
- Only the review step receives the provider key.
  `tests/test_review_workflow.py` covers this with
  `test_api_key_reaches_review`.

Local modes (`file`, `piece`, `wholesale`) run through `engine/run_eval.py`
on a workstation. A local run sends `QUALITY.md` and one eval case to the
callable that `--model-call` names. The person running the command chooses
that callable and its provider.
