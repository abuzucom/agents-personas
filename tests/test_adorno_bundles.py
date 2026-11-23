#!/usr/bin/env python3
"""The committed bundle artifacts.

test_build_bundle.py asserts the producing logic. This module asserts the
committed output. Every assertion here is manifest-driven, so it holds for
whatever scopes and tiers bundles.json declares.
"""

import importlib.util
import re
import unittest
from pathlib import Path

# Ported from abuzucom/adorno tests/test_bundles.py at 97a2c84. REPO_ROOT names the
# adorno persona directory.
REPO_ROOT = Path(__file__).resolve().parent.parent / "reviewers" / "adorno"
BUNDLES_DIR = REPO_ROOT / "bundles"
CHECKS_DIR = REPO_ROOT / "docs" / "checks"
BUILDER_PATH = REPO_ROOT / "scripts" / "build_bundle.py"
REPO_PATH_PATTERN = re.compile(r"`(docs/checks/[A-Za-z0-9._-]+\.md)`")


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_bundle", BUILDER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = _load_builder()
MANIFEST = builder.load_manifest(REPO_ROOT)


def declared_pairs():
    """Yield every scope and tier the manifest declares."""
    for scope in sorted(MANIFEST):
        for tier in sorted(MANIFEST[scope]):
            yield scope, tier


def bundle_path(scope: str, tier: str) -> Path:
    return builder.output_path(REPO_ROOT, scope, tier)


class CurrencyTest(unittest.TestCase):
    """Every committed bundle matches its sources."""

    def test_check_mode_passes(self):
        self.assertEqual(builder.main([str(REPO_ROOT), "--check"]), 0)


class ManifestPairingTest(unittest.TestCase):
    """Manifest entries and committed bundles correspond exactly."""

    def test_every_declared_tier_is_committed(self):
        for scope, tier in declared_pairs():
            with self.subTest(scope=scope, tier=tier):
                self.assertTrue(bundle_path(scope, tier).is_file())

    def test_no_orphan_bundle(self):
        expected = {bundle_path(scope, tier).name for scope, tier in declared_pairs()}
        actual = {path.name for path in BUNDLES_DIR.glob("*.md")}
        self.assertEqual(sorted(actual - expected), [])


class SourceResolutionTest(unittest.TestCase):
    """Every manifest source glob resolves to at least one file."""

    def test_every_glob_resolves(self):
        for scope, tiers in MANIFEST.items():
            for tier, patterns in tiers.items():
                with self.subTest(scope=scope, tier=tier):
                    resolved = builder.resolve_sources(REPO_ROOT, patterns)
                    self.assertTrue(resolved)


class DeadPointerTest(unittest.TestCase):
    """A full bundle resolves every repository path it names.

    A pasted AUDIT.md ending each class in Detail: docs/checks/2.N.md hands
    the model a pointer it cannot follow. The model then infers content
    absent from its context, which is worse than a monolith. This assertion
    is the reason the bundle exists.
    """

    def test_full_tier_carries_every_path_it_references(self):
        for scope, tier in declared_pairs():
            if tier != "full":
                continue
            text = bundle_path(scope, tier).read_text(encoding="utf-8")
            listed = set(re.findall(r"^- `(.+)`$", text, re.MULTILINE))
            for reference in set(REPO_PATH_PATTERN.findall(text)):
                if reference not in listed:
                    continue
                stem = Path(reference).stem
                with self.subTest(scope=scope, reference=reference):
                    self.assertIn(stem, text)


class HeaderTest(unittest.TestCase):
    """Every bundle states what it is."""

    def test_header_names_scope_and_tier(self):
        for scope, tier in declared_pairs():
            with self.subTest(scope=scope, tier=tier):
                first = bundle_path(scope, tier).read_text(encoding="utf-8").splitlines()[0]
                self.assertIn(scope, first)
                self.assertIn(tier, first)

    def test_header_marks_the_file_generated(self):
        for scope, tier in declared_pairs():
            with self.subTest(scope=scope, tier=tier):
                text = bundle_path(scope, tier).read_text(encoding="utf-8")
                self.assertIn("scripts/build_bundle.py", text)
                self.assertIn("Do not edit", text)


class ClassContentTest(unittest.TestCase):
    """A full bundle carries every check file the repository ships."""

    def test_full_tier_carries_every_class(self):
        expected = sorted(path.stem for path in CHECKS_DIR.glob("2.*.md"))
        self.assertTrue(expected)
        for scope, tier in declared_pairs():
            if tier != "full":
                continue
            text = bundle_path(scope, tier).read_text(encoding="utf-8")
            for number in expected:
                with self.subTest(scope=scope, number=number):
                    self.assertIn(f"# {number} ", text)


if __name__ == "__main__":
    unittest.main()
