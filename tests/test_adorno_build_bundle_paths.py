"""Test that the adorno bundle builder writes only inside the persona root.

A symlinked bundles/ directory points the output anywhere on disk. The
builder refuses that directory in build and check modes. It also refuses a
bundle file that is a symlink. No file outside the root changes.
"""

import os
import pathlib
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from retrying_temp_directory import RetryingTemporaryDirectory
from test_adorno_build_bundle import build_tree, builder

BUNDLE_NAME = "ui-full.md"


class OutputContainmentTest(unittest.TestCase):
    """Bundles land in a real bundles/ directory under the persona root."""

    def setUp(self):
        temp = RetryingTemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = pathlib.Path(temp.name)
        self.root = build_tree(str(self.base / "root"))
        self.outside = self.base / "outside"
        self.outside.mkdir()

    def link(self, link: pathlib.Path, target: pathlib.Path, target_is_directory: bool = False) -> None:
        """Create a symlink, skipping only when the platform denies it."""
        try:
            link.symlink_to(target, target_is_directory=target_is_directory)
        except OSError as error:
            self.skipTest(f"platform denied symlink creation: {error}")

    def link_bundles_outside(self) -> None:
        (self.root / "bundles").rmdir()
        self.link(self.root / "bundles", self.outside, target_is_directory=True)

    def test_regular_bundles_directory_builds(self):
        self.assertEqual(builder.main([str(self.root)]), 0)
        self.assertTrue((self.root / "bundles" / BUNDLE_NAME).is_file())

    def test_symlinked_bundles_directory_is_refused(self):
        self.link_bundles_outside()
        with self.assertRaisesRegex(builder.BundleError, "bundles/ is a symlink"):
            builder.output_path(self.root, "ui", "full")

    def test_build_writes_nothing_through_a_symlinked_directory(self):
        self.link_bundles_outside()
        self.assertEqual(builder.main([str(self.root)]), 1)
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_check_refuses_a_symlinked_directory(self):
        self.link_bundles_outside()
        (self.outside / BUNDLE_NAME).write_text("stale\n", encoding="utf-8")
        self.assertEqual(builder.main([str(self.root), "--check"]), 1)

    def test_symlinked_bundle_file_is_refused(self):
        target = self.outside / "target.md"
        target.write_text("keep\n", encoding="utf-8")
        self.link(self.root / "bundles" / BUNDLE_NAME, target)
        self.assertEqual(builder.main([str(self.root)]), 1)
        self.assertEqual(target.read_text(encoding="utf-8"), "keep\n")

    def test_unresolved_root_still_builds(self):
        unresolved = self.root / "docs" / ".."
        self.assertEqual(builder.main([str(unresolved)]), 0)
        self.assertTrue((self.root / "bundles" / BUNDLE_NAME).is_file())


if __name__ == "__main__":
    unittest.main()
