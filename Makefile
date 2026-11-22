.PHONY: sync check lint lint-code test identity changelog

# Overridable so a platform without this name can supply its own:
#   make test PYTHON=py
PYTHON ?= python3

PROSE_FILES = AGENTS.md README.md CHANGELOG.md \
	docs/project-orientation.md docs/template-drift.md

sync:
	$(PYTHON) scripts/sync.py

check:
	$(PYTHON) scripts/sync.py --check

changelog:
	$(PYTHON) scripts/check_changelog.py

lint:
	$(PYTHON) scripts/lint_style.py
	$(PYTHON) scripts/check_us_spelling.py $(PROSE_FILES)
	$(PYTHON) scripts/check_english_only.py $(PROSE_FILES)
	$(PYTHON) scripts/check_hedging.py $(PROSE_FILES)
	$(PYTHON) scripts/check_anti_delegation.py $(PROSE_FILES)
	$(PYTHON) scripts/check_conflict_markers.py

test:
	$(PYTHON) scripts/run_tests.py

# Code lint for the engine, the personas, and the matching tests. It needs
#   python -m pip install --require-hashes -r requirements-dev.txt
# make lint stays standard-library only. --ignore-noqa makes suppression
# comments ineffective. The warn tier reports and never fails. The persona
# eval cases hold planted defects. Every tool skips those cases.
LINT_TESTS = $(wildcard tests/test_engine_*.py tests/test_euler_*.py tests/test_foucault_*.py \
	tests/test_generay_*.py tests/test_scan_request_label.py)
RUFF_PATHS = engine reviewers $(LINT_TESTS)
RUFF_EXCLUDE = --force-exclude --extend-exclude 'reviewers/*/eval/cases'
MYPY_PERSONAS = foucault euler generay
# Workflows adopted from the abuzucom/agents template stay out of scope.
# The template repository owns the layout of those files.
YAML_PATHS = .yamllint.yml examples .github/workflows/review.yml \
	.github/workflows/euler-quality-review.yml .github/workflows/euler-quality-review-pr.yml \
	.github/workflows/foucault-security-review.yml .github/workflows/foucault-security-review-pr.yml \
	.github/workflows/generay-time-review.yml .github/workflows/generay-time-review-pr.yml \
	.github/workflows/stop-requested-notice.yml .github/workflows/sandbox-check.yml \
	.github/workflows/lint-code.yml

lint-code:
	$(PYTHON) -m ruff check --ignore-noqa $(RUFF_EXCLUDE) $(RUFF_PATHS)
	$(PYTHON) -m ruff format --check $(RUFF_EXCLUDE) $(RUFF_PATHS)
	$(PYTHON) -m ruff check --config ruff.warn.toml --ignore-noqa --exit-zero $(RUFF_EXCLUDE) $(RUFF_PATHS)
	cd engine && $(PYTHON) -m mypy --config-file ../mypy.ini .
	for persona in $(MYPY_PERSONAS); do \
		(cd reviewers/$$persona && MYPYPATH=scripts:../../engine $(PYTHON) -m mypy --config-file ../../mypy.ini .) \
			|| exit 1; \
	done
	$(PYTHON) -m yamllint --strict $(YAML_PATHS)

identity:
	$(PYTHON) scripts/check_git_identity.py --advise
