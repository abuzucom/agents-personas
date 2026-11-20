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
- Adopt the `abuzucom/agents` policy at commit
  `909b93702273befaec9227ee892fe1a2261a4a41`. The adoption covers
  `AGENTS.md`, the synchronized client copies, and `docs/agent-policy/`.
- Adopt the complete gate set for Claude Code, Codex, Gemini, and
  Antigravity. `scripts/complete_gate_adoption.py` installed the staged
  candidate. `scripts/check_gate_adoption.py` passes.
- Adopt the checkers, the test suite, `Makefile`, `.pre-commit-config.yaml`,
  and the CI workflows `agents-compliance.yml`, `agents-md-compliance.yml`,
  `gate-integrity.yml`, `immutable-conflict-check.yml`,
  `policy-size-report.yml`, and `sync-check.yml`.
- Add `docs/plans/consolidation.md`. The plan moves the five PR reviewer
  repositories into this repository on one shared review engine.
- Add `docs/project-orientation.md`.
