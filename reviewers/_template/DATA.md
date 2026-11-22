# Data sent to the model provider

Replace this file with the data statement of the new persona.

The statement lists every item the persona sends to the provider. The
engine rule allows two items only:

- the fenced pull request content (diff, title, body, and file names)
- the persona prompt for the requested mode

A persona with `review_hooks.py` can add hook items, such as prescan
candidates. The engine places hook items in `REVIEW_TARGET` as untrusted
data. List each hook item the persona sends.

A mode prompt can name one file or a list of files. List every file the
review mode sends.

An option marked `"trusted": true` sends its value in
`TRUSTED_CONTEXT.options`. Only the caller workflow sets that value. List
each trusted option the persona sends.

Name any narrower limit the persona applies. Name the test that enforces
each limit.
