"""Unit tests for the prolong CLI."""
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from prolong.cli import main


class TestCli(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.home = Path(self.temp_dir.name).resolve()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_cli_version(self):
        with self.assertRaises(SystemExit) as cm, patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            main(["--version"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("prolong 0.1.1", mock_out.getvalue())

    def test_cli_local_lifecycle(self):
        project = self.home / "repo"
        project.mkdir()

        # 1. init
        with self.assertRaises(SystemExit) as cm, patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            main(["init", "--dir", str(project), "--client", "claude-code"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("PRO-LONG initialized in", mock_out.getvalue())
        self.assertTrue((project / ".prolong" / "log.jsonl").exists())

        # 2. status
        with self.assertRaises(SystemExit) as cm, patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            main(["status", "--dir", str(project)])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("Project Installed:  yes", mock_out.getvalue())

        # 3. deinit
        with self.assertRaises(SystemExit) as cm, patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            main(["deinit", "--dir", str(project), "--purge"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("PRO-LONG deinitialized from", mock_out.getvalue())
        self.assertFalse((project / ".prolong").exists())

    def test_cli_global_lifecycle(self):
        with patch.dict(os.environ, {"HOME": str(self.home)}), patch("pathlib.Path.home", return_value=self.home):
            # 1. global init
            with self.assertRaises(SystemExit) as cm, patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                main(["init", "--global", "--client", "claude-code,codex"])
            self.assertEqual(cm.exception.code, 0)
            self.assertIn("PRO-LONG initialized globally", mock_out.getvalue())
            self.assertTrue((self.home / ".prolong" / "runtime.py").exists())

            # 2. global status
            with self.assertRaises(SystemExit) as cm, patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                main(["status", "--global"])
            self.assertEqual(cm.exception.code, 0)
            self.assertIn("Installed:       yes", mock_out.getvalue())

            # 3. global deinit
            with self.assertRaises(SystemExit) as cm, patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                main(["deinit", "--global", "--purge"])
            self.assertEqual(cm.exception.code, 0)
            self.assertIn("PRO-LONG deinitialized globally", mock_out.getvalue())
            self.assertFalse((self.home / ".prolong").exists())


if __name__ == "__main__":
    unittest.main()
