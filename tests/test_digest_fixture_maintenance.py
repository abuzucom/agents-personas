#!/usr/bin/env python3
"""Keep Git background maintenance out of the digest index fixture.

BackfillHistory in tests/test_sync_digest_index.py commits into a template
repository and then copies it with shutil.copytree. Git 2.56 starts
detached auto maintenance after a commit. That process creates and removes
.git/objects/maintenance.lock during the copy. copytree then fails with
FileNotFoundError on the vanished lock. The fixture must disable automatic
maintenance and automatic garbage collection in the template repository.
"""
import subprocess
import unittest

try:
    from tests import test_sync_digest_index
except ImportError:
    import test_sync_digest_index


def read_template_config(history, key: str) -> str:
    """Return one local Git config value of the fixture template repository."""
    result = subprocess.run(
        ["git", "-C", str(history.template), "config", "--local", "--get", key],
        capture_output=True, text=True, check=False,
    )
    return result.stdout.strip()


class DigestFixtureMaintenanceTest(unittest.TestCase):
    """Require a template repository that starts no background maintenance."""

    @classmethod
    def setUpClass(cls):
        cls.history = test_sync_digest_index.BackfillHistory(cls.addClassCleanup)

    def test_template_disables_auto_maintenance(self):
        self.assertEqual(read_template_config(self.history, "maintenance.auto"), "false")

    def test_template_disables_auto_garbage_collection(self):
        self.assertEqual(read_template_config(self.history, "gc.auto"), "0")


if __name__ == "__main__":
    unittest.main()
