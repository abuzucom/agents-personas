# Changelog

This file documents every notable project change.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
One deviation applies. A version heading parenthesizes the release date.
The format uses `## [1.2.3] (2026-01-01)` instead of a spaced hyphen.
The house style bans that hyphen. `scripts/check_ascii.py` enforces the ban on
this file.
All dates are UTC.
Each date has one entry. Every change still advances the version. A same-day
change renames that day's heading to the new version and merges its items
into the entry. Dates never decrease. Ask the active human when a date is in
doubt.
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] (2026-11-20)

### Added
- Add `engine/envelope.py`. The JSON review envelope places the title,
  body, file names, and patches inside `REVIEW_TARGET` only. The engine
  caps the title and body and records each truncation. `with_fence_rule`
  appends the untrusted input rule to the persona prompt.
- Add `engine/build_pr_case.py`, ported from `abuzucom/euler` without the
  euler prescan. It reads the diff from git objects and splits it into
  chunks under the mode byte budget. Unreviewable files land in the
  manifest.
- Add optional `max_chunks` and `max_envelope_bytes` caps to each
  `reviewer.json` mode. `resolve_caps` lets a caller lower a cap and clamps
  a higher request.
- Add the shared injection corpus in `engine/eval/injection/`. It covers
  the title, body, path, and patch vectors.
- Add `engine/model_providers.json`, the single provider table.
- Add `engine/call_model.py`, ported from `abuzucom/foucault`. It reports
  token usage per request and writes it to `USAGE_FILE`. `MODEL_PROVIDER`
  selects a table entry by name. A transient status gets one retry.
- Add `engine/run_model_command.py`, ported from `abuzucom/foucault`. It
  runs the caller's adapter script without a shell. The script must stay
  inside the caller workspace. The runner refuses backslashes and drive
  prefixes in the command.
- Add `engine/check_review_response.py`, ported from `abuzucom/foucault`.
  It enforces the shared verdict contract, the expected mode, and a file
  and line for each finding.
- Add the persona manifest schema in `engine/reviewers.py`. A manifest
  declares modes with review delivery, context delivery, or both. Exactly
  one mode is the default.
- Add `engine/check_reviewers.py`. It validates every
  `reviewers/<name>/reviewer.json` and the template.
- Add `engine/render_context.py`. It prints one context-delivery mode for
  an agent prompt. The output equals the prompt bytes on every platform.
- Add the `reviewers/_template/` scaffold for a new persona.
- Record decisions 16, 21, and 22 in `docs/plans/consolidation.md`. The
  engine accepts `APPROVE`, `BLOCK`, and `NEEDS-HUMAN`. A non-gating
  verdict sets the mode check to `neutral`. Engine workflows use the euler
  and generay action pins.

### Fixed
- Ignore `.comment-drafts/`. The directory holds comment and pull request
  body drafts for `scripts/trusted_gh.py` and never belongs in commits.
- Disable automatic Git maintenance in the digest index test fixture. The
  fixture copy failed when detached maintenance removed its lock file.

### Added
- Add `docs/plans/consolidation.md`. The plan moves the five PR checker
  repositories into this repository.
- Adopt the agents policy from `abuzucom/agents` at
  `909b93702273befaec9227ee892fe1a2261a4a41`.
- Add `AGENTS.md` and its synchronized client copies.
- Add the complete gate set for claude, codex, gemini, and antigravity.
  The set covers hooks, client registrations, shared modules, checkers,
  tests, and `shared-files.json`.
- Add the local-path checker with an approved `.local-path-allowlist`.
- Add the `sync-check`, `agents-compliance`, `agents-md-compliance`, and
  `gate-integrity` workflows.
- Add `requirements-checkers.txt` with hash-pinned PyYAML 6.0.3.
- Add `docs/project-orientation.md` and `docs/template-drift.md`.
