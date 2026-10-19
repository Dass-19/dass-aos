"""Tests for the pre-commit guard (deny_paths) in .aos/hooks/pre_commit.py."""
import importlib.util
import shutil
import unittest
from pathlib import Path

from dass_aos.constants import DEFAULT_DENY_PATHS

HOOK = Path(__file__).resolve().parent.parent / "dass_aos" / "templates" / "hooks" / "pre_commit.py"


def load_hook():
    spec = importlib.util.spec_from_file_location("aos_pre_commit", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestPreCommitGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hook = load_hook()

    def test_env_and_credentials_are_blocked(self):
        for path in [".env", "config/.env", ".env.production", "certs/server.pem", "keys/id_rsa", ".ssh/config"]:
            self.assertTrue(self.hook.blocked([path], DEFAULT_DENY_PATHS), path)

    def test_ssh_directory_matches_nested_paths(self):
        self.assertTrue(self.hook.blocked(["home/user/.ssh/config"], [".ssh/"]))
        self.assertEqual(self.hook.blocked(["src/.envrc"], [".env"]), [])

    def test_regular_source_files_are_not_blocked(self):
        self.assertEqual(self.hook.blocked(["src/app.py", "README.md", "docs/env.md"], DEFAULT_DENY_PATHS), [])

    def test_allowlist_is_empty_by_default(self):
        import os
        import tempfile

        previous = os.getcwd()
        empty = Path(tempfile.mkdtemp())
        os.chdir(empty)
        try:
            self.assertEqual(self.hook.deny_paths(), [])
        finally:
            os.chdir(previous)
            shutil.rmtree(empty, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
