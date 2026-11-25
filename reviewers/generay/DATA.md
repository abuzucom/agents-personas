# Data sent to the model provider

generay sends the provider three items per review chunk:

- the fenced pull request content: the diff, title, body, and file names
- the prescan candidates for the files of that chunk, in `REVIEW_TARGET`
- `TIME.md` and `SYNC.md`, the persona prompts for the time mode

A prescan candidate holds a changed file path, a line number, a TIME.md or
SYNC.md check ID, its method tag, a checker message, and a blocking flag. No
time check blocks. A checker message can quote a short excerpt of the changed
file. The same text already appears in the diff.

`TIME.md` names `data/libraries.json` as the source of favored libraries. The
review sends no part of that file. The prompt carries no registry content.

The provider receives no GitHub token, no provider configuration file, and no
other repository secret. The prescan runs in the build step. That step holds
no secret. Every generay hook runs in a child process with an allowlisted
environment that holds no credential. The child starts in an empty
temporary home. Bubblewrap runs each hook without network access. A run
without a trusted `/usr/bin/bwrap` fails closed unless
`PERSONAS_REQUIRE_SANDBOX=0` allows a local fallback. The hook sees only
`/usr`, five runtime files in `/etc`, the Python installation, the engine,
the persona, and the head tree copy (decision 33). Only the review step
holds `MODEL_API_KEY`.

`tests/test_generay_review_hooks.py` covers the prescan placement with
`test_prescan_rides_review_target`. The engine tests named in
`reviewers/euler/DATA.md` cover the envelope, the chunk split, and the step
secrets for every persona.

Local modes (`file`, `piece`, `wholesale`, `contract`) run through
`engine/run_eval.py` on a workstation. A local run sends `TIME.md`, `SYNC.md`,
and one eval case to the callable that `--model-call` names. The person
running the command chooses that callable and its provider. The `sync` mode
renders `SYNC.md` for an agent prompt through `engine/render_context.py`.
