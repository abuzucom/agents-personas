"""Test the persona manifest schema, its checker, and context rendering."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_DIR = REPO_ROOT / "engine"


def _load(name: str):
    """Load one engine module by path, the way the workflows run it."""
    spec = importlib.util.spec_from_file_location(name, ENGINE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


reviewers = _load("reviewers")

GENERAY = {
    "persona": "generay",
    "function": "time",
    "modes": {
        "time": {"prompt": "TIME.md", "review": True, "default": True},
        "sync": {"prompt": "SYNC.md", "review": True, "context": True},
    },
}


def _write_persona(root: Path, name: str, manifest: dict, prompts=("TIME.md", "SYNC.md")):
    """Create reviewers/<name>/ with a manifest and prompt files."""
    persona_dir = root / "reviewers" / name
    persona_dir.mkdir(parents=True)
    (persona_dir / "reviewer.json").write_text(json.dumps(manifest), encoding="utf-8")
    for prompt in prompts:
        (persona_dir / prompt).write_text(f"# {prompt}\nReview rules.\n", encoding="ascii")
    return persona_dir


def _with(manifest: dict, **changes) -> dict:
    """Return a deep copy of a manifest with top-level keys replaced."""
    copy = json.loads(json.dumps(manifest))
    copy.update(changes)
    return copy


class ManifestValidationTest(unittest.TestCase):
    """validate_persona reports every schema defect by name."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def findings(self, manifest: dict, name: str = "generay", prompts=("TIME.md", "SYNC.md")):
        persona_dir = _write_persona(self.root, name, manifest, prompts)
        return reviewers.validate_persona(persona_dir)

    def test_valid_two_mode_manifest_has_no_findings(self):
        self.assertEqual(self.findings(GENERAY), [])

    def test_missing_default_mode_is_reported(self):
        manifest = _with(GENERAY)
        del manifest["modes"]["time"]["default"]
        self.assertTrue(any("exactly one default mode" in item for item in self.findings(manifest)))

    def test_two_default_modes_are_reported(self):
        manifest = _with(GENERAY)
        manifest["modes"]["sync"]["default"] = True
        self.assertTrue(any("exactly one default mode" in item for item in self.findings(manifest)))

    def test_missing_prompt_file_is_reported(self):
        findings = self.findings(GENERAY, prompts=("TIME.md",))
        self.assertTrue(any("SYNC.md" in item and "missing" in item for item in findings))

    def test_mode_without_delivery_is_reported(self):
        manifest = _with(GENERAY)
        manifest["modes"]["sync"] = {"prompt": "SYNC.md", "review": False, "context": False}
        self.assertTrue(any("no delivery" in item for item in self.findings(manifest)))

    def test_prompt_path_escaping_persona_is_reported(self):
        manifest = _with(GENERAY)
        manifest["modes"]["sync"]["prompt"] = "../outside.md"
        self.assertTrue(any("escapes" in item for item in self.findings(manifest)))

    def test_absolute_prompt_path_is_reported(self):
        manifest = _with(GENERAY)
        manifest["modes"]["sync"]["prompt"] = "/etc/passwd"
        self.assertTrue(any("escapes" in item for item in self.findings(manifest)))

    def test_persona_field_must_match_directory(self):
        findings = self.findings(_with(GENERAY, persona="euler"))
        self.assertTrue(any("does not match directory" in item for item in findings))

    def test_unknown_top_level_key_is_reported(self):
        findings = self.findings(_with(GENERAY, extra=1))
        self.assertTrue(any("unknown key 'extra'" in item for item in findings))

    def test_unknown_mode_key_is_reported(self):
        manifest = _with(GENERAY)
        manifest["modes"]["time"]["weight"] = 2
        self.assertTrue(any("unknown key 'weight'" in item for item in self.findings(manifest)))

    def test_non_boolean_flag_is_reported(self):
        manifest = _with(GENERAY)
        manifest["modes"]["time"]["review"] = "yes"
        self.assertTrue(any("must be true or false" in item for item in self.findings(manifest)))

    def test_invalid_mode_name_is_reported(self):
        manifest = _with(GENERAY)
        manifest["modes"]["Sync--Mode"] = manifest["modes"].pop("sync")
        self.assertTrue(any("invalid mode name" in item for item in self.findings(manifest)))

    def test_invalid_persona_directory_name_is_reported(self):
        findings = self.findings(_with(GENERAY, persona="Bad_Name"), name="Bad_Name")
        self.assertTrue(any("invalid persona name" in item for item in findings))

    def test_malformed_json_is_reported(self):
        persona_dir = self.root / "reviewers" / "generay"
        persona_dir.mkdir(parents=True)
        (persona_dir / "reviewer.json").write_text("{not json", encoding="utf-8")
        self.assertTrue(any("not valid JSON" in item for item in reviewers.validate_persona(persona_dir)))

    def test_missing_manifest_is_reported(self):
        persona_dir = self.root / "reviewers" / "generay"
        persona_dir.mkdir(parents=True)
        self.assertTrue(any("reviewer.json is missing" in item for item in reviewers.validate_persona(persona_dir)))

    def test_empty_modes_map_is_reported(self):
        findings = self.findings(_with(GENERAY, modes={}))
        self.assertTrue(any("declares no modes" in item for item in findings))


class ReviewModeResolutionTest(unittest.TestCase):
    """resolve_review_modes picks the default and rejects bad requests."""

    def test_empty_request_selects_the_default_mode(self):
        self.assertEqual(reviewers.resolve_review_modes(GENERAY, ""), ["time"])

    def test_listed_modes_keep_request_order_without_duplicates(self):
        self.assertEqual(
            reviewers.resolve_review_modes(GENERAY, "sync, time,sync"), ["sync", "time"])

    def test_unknown_mode_is_rejected(self):
        with self.assertRaisesRegex(reviewers.ReviewerError, "unknown mode 'audit'"):
            reviewers.resolve_review_modes(GENERAY, "time,audit")

    def test_mode_without_review_delivery_is_rejected(self):
        manifest = _with(GENERAY)
        manifest["modes"]["sync"]["review"] = False
        with self.assertRaisesRegex(reviewers.ReviewerError, "no review delivery"):
            reviewers.resolve_review_modes(manifest, "sync")


class CheckReviewersCliTest(unittest.TestCase):
    """engine/check_reviewers.py exits nonzero on any defect."""

    def run_checker(self, root: Path):
        return subprocess.run(
            [sys.executable, str(ENGINE_DIR / "check_reviewers.py"), "--root", str(root)],
            capture_output=True, text=True, check=False)

    def test_valid_tree_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_persona(root, "generay", GENERAY)
            result = self.run_checker(root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("1 persona", result.stdout)

    def test_defective_tree_fails_with_finding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_persona(root, "generay", _with(GENERAY, persona="euler"))
            result = self.run_checker(root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not match directory", result.stderr)

    def test_missing_reviewers_directory_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_checker(Path(directory))
        self.assertEqual(result.returncode, 1)
        self.assertIn("reviewers/ is missing", result.stderr)

    def test_live_repository_passes(self):
        result = self.run_checker(REPO_ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)


class RenderContextCliTest(unittest.TestCase):
    """engine/render_context.py prints only context-delivery modes."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        _write_persona(self.root, "generay", GENERAY)

    def tearDown(self):
        self.temp.cleanup()

    def render(self, persona: str, mode: str):
        return subprocess.run(
            [sys.executable, str(ENGINE_DIR / "render_context.py"), "--root", str(self.root),
             "--persona", persona, "--mode", mode],
            capture_output=True, text=True, check=False)

    def test_context_mode_prints_its_prompt(self):
        result = self.render("generay", "sync")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "# SYNC.md\nReview rules.\n")

    def test_review_only_mode_is_refused(self):
        result = self.render("generay", "time")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no context delivery", result.stderr)

    def test_unknown_persona_is_refused(self):
        result = self.render("nobody", "sync")
        self.assertEqual(result.returncode, 1)
        self.assertIn("unknown persona 'nobody'", result.stderr)

    def test_path_like_persona_is_refused(self):
        result = self.render("../generay", "sync")
        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid persona name", result.stderr)

    def test_non_ascii_prompt_is_refused(self):
        sync = self.root / "reviewers" / "generay" / "SYNC.md"
        sync.write_bytes("café\n".encode())
        result = self.render("generay", "sync")
        self.assertEqual(result.returncode, 1)
        self.assertIn("not ASCII", result.stderr)

    def test_oversized_prompt_is_refused(self):
        sync = self.root / "reviewers" / "generay" / "SYNC.md"
        sync.write_text("x" * (reviewers.MAX_CONTEXT_BYTES + 1), encoding="ascii")
        result = self.render("generay", "sync")
        self.assertEqual(result.returncode, 1)
        self.assertIn("exceeds", result.stderr)


class TemplateTest(unittest.TestCase):
    """reviewers/_template/ stays a valid scaffold outside the persona list."""

    def test_template_validates(self):
        self.assertEqual(reviewers.validate_persona(REPO_ROOT / "reviewers" / "_template"), [])

    def test_template_is_not_a_runnable_persona(self):
        self.assertNotIn("_template", reviewers.list_personas(REPO_ROOT))

    def test_template_carries_data_statement(self):
        self.assertTrue((REPO_ROOT / "reviewers" / "_template" / "DATA.md").is_file())


if __name__ == "__main__":
    unittest.main()
