"""Unit tests for LongMem runtime."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from longmem.runtime import (
    init_longmem_dir,
    is_self_read,
    record,
    resolve_workspace_root,
)


class TestRuntime(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name).resolve()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_init_longmem_dir(self):
        longmem_dir = init_longmem_dir(self.root)
        self.assertTrue(longmem_dir.is_dir())

        gitignore = longmem_dir / ".gitignore"
        self.assertTrue(gitignore.is_file())
        self.assertEqual(gitignore.read_text(encoding="utf-8"), "*\n")

        log_file = longmem_dir / "log.jsonl"
        self.assertTrue(log_file.is_file())

    def test_resolve_workspace_root_git(self):
        # Initialize a temporary git repository
        subprocess.run(["git", "init", str(self.root)], capture_output=True, check=True)
        sub_dir = self.root / "sub" / "folder"
        sub_dir.mkdir(parents=True)

        resolved = resolve_workspace_root(candidate=sub_dir)
        self.assertEqual(resolved, self.root)

    def test_resolve_workspace_root_non_git(self):
        resolved = resolve_workspace_root(candidate=self.root)
        self.assertEqual(resolved, self.root)

    def test_is_self_read(self):
        self.assertFalse(is_self_read(None))
        self.assertFalse(is_self_read({"command": "git status"}))
        self.assertTrue(is_self_read({"command": "rg foo .longmem/log.jsonl"}))
        self.assertTrue(is_self_read("cat .longmem/log.jsonl"))

    def test_record_lifecycle_events(self):
        # 1. Session start
        record(
            "codex",
            {"hook_event_name": "SessionStart", "session_id": "sess-1"},
            root=self.root,
        )

        log_file = self.root / ".longmem" / "log.jsonl"
        self.assertTrue(log_file.exists())
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)

        entry1 = json.loads(lines[0])
        self.assertEqual(entry1["client"], "codex")
        self.assertEqual(entry1["sessionId"], "sess-1")
        self.assertEqual(entry1["type"], "session_start")

        # 2. User prompt
        record(
            "codex",
            {"hook_event_name": "UserPromptSubmit", "session_id": "sess-1", "prompt": "Refactor auth"},
            root=self.root,
        )
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 2)
        entry2 = json.loads(lines[1])
        self.assertEqual(entry2["type"], "user_prompt")
        self.assertEqual(entry2["content"]["prompt"], "Refactor auth")

        # 3. Tool self-read should be ignored
        record(
            "codex",
            {
                "hook_event_name": "PostToolUse",
                "session_id": "sess-1",
                "tool_input": {"command": "rg auth .longmem/log.jsonl"},
            },
            root=self.root,
        )
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 2, "self-reads of .longmem/log.jsonl must be filtered out")

        # 4. Normal tool call
        record(
            "codex",
            {
                "hook_event_name": "PostToolUse",
                "session_id": "sess-1",
                "tool_input": {"command": "pytest"},
            },
            root=self.root,
        )
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 3)

    def test_subprocess_execution(self):
        runtime_py = Path(__file__).resolve().parent.parent / "longmem" / "runtime.py"
        event = {
            "hook_event_name": "SessionStart",
            "session_id": "subp-1",
            "cwd": str(self.root),
        }
        res = subprocess.run(
            [sys.executable, str(runtime_py), "--hook", "claude-code"],
            input=json.dumps(event),
            text=True,
            capture_output=True,
            cwd=str(self.root),
            check=False,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("{}", res.stdout)

        log_file = self.root / ".longmem" / "log.jsonl"
        self.assertTrue(log_file.exists())
        gitignore = self.root / ".longmem" / ".gitignore"
        self.assertTrue(gitignore.exists())
        self.assertEqual(gitignore.read_text(encoding="utf-8"), "*\n")


if __name__ == "__main__":
    unittest.main()
