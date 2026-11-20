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

## [0.1.0] (2026-11-20)

### Added
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
