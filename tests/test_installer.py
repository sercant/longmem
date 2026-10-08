"""Unit tests for PRO-LONG installer and uninstaller."""
import json
import tempfile
import unittest
from pathlib import Path

from prolong.installer import (
    check_global_status,
    check_project_status,
    init_global,
    init_project,
    uninstall_global,
    uninstall_project,
)


class TestInstaller(unittest.TestCase):
    def setUp(self):
        self.temp_home = tempfile.TemporaryDirectory()
        self.home = Path(self.temp_home.name).resolve()

    def tearDown(self):
        self.temp_home.cleanup()

    def test_global_install_preserves_existing_hooks_and_rules(self):
        # Pre-seed existing configurations
        claude_dir = self.home / ".claude"
        claude_dir.mkdir(parents=True)
        existing_claude_settings = {
            "permissions": {"defaultMode": "auto"},
            "hooks": {
                "SessionStart": [
                    {
                        "hooks": [
                            {"type": "command", "command": "python3 /some/other/hook.py"}
                        ]
                    }
                ]
            },
        }
        (claude_dir / "settings.json").write_text(json.dumps(existing_claude_settings), encoding="utf-8")
        (claude_dir / "CLAUDE.md").write_text("# Existing user guidelines\n\n- Think carefully\n", encoding="utf-8")

        codex_dir = self.home / ".codex"
        codex_dir.mkdir(parents=True)
        existing_codex_hooks = {
            "hooks": {
                "UserPromptSubmit": [
                    {
                        "hooks": [
                            {"type": "command", "command": "echo existing"}
                        ]
                    }
                ]
            }
        }
        (codex_dir / "hooks.json").write_text(json.dumps(existing_codex_hooks), encoding="utf-8")
        (codex_dir / "AGENTS.md").write_text("# Existing codex rules\n", encoding="utf-8")

        # Run global init
        manifest = init_global(clients=["claude-code", "codex"], home=self.home)
        self.assertEqual(manifest["scope"], "global")
        self.assertIn("claude-code", manifest["clients"])
        self.assertIn("codex", manifest["clients"])

        # Verify global runtime
        runtime_path = self.home / ".prolong" / "runtime.py"
        self.assertTrue(runtime_path.exists())

        # Verify skills
        self.assertTrue((self.home / ".claude" / "skills" / "prolong" / "SKILL.md").exists())
        self.assertTrue((self.home / ".agents" / "skills" / "prolong" / "SKILL.md").exists())

        # Verify claude settings kept the other hook and added prolong
        updated_claude = json.loads((claude_dir / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(updated_claude["permissions"]["defaultMode"], "auto")
        session_start_groups = updated_claude["hooks"]["SessionStart"]
        self.assertEqual(len(session_start_groups), 2, "existing hook plus prolong hook")
        self.assertEqual(session_start_groups[0]["hooks"][0]["command"], "python3 /some/other/hook.py")
        self.assertIn("prolong/runtime.py", session_start_groups[1]["hooks"][0]["args"][0])

        # Verify CLAUDE.md kept existing rules and appended prolong
        claude_md = (claude_dir / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("# Existing user guidelines", claude_md)
        self.assertIn("<!-- prolong:start -->", claude_md)

        # Verify codex AGENTS.md
        agents_md = (codex_dir / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("# Existing codex rules", agents_md)
        self.assertIn("<!-- prolong:start -->", agents_md)

        # Check status
        status = check_global_status(home=self.home)
        self.assertTrue(status["installed"])
        self.assertTrue(status["claude_code"]["installed"])
        self.assertTrue(status["codex"]["installed"])

        # Re-running init should be idempotent
        init_global(clients=["claude-code", "codex"], home=self.home)
        updated_claude_2 = json.loads((claude_dir / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(len(updated_claude_2["hooks"]["SessionStart"]), 2, "must not duplicate hooks")

        # Uninstall global
        uninstall_global(home=self.home, purge=False)
        claude_after_un = json.loads((claude_dir / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(len(claude_after_un["hooks"]["SessionStart"]), 1, "prolong hook removed, other preserved")
        self.assertEqual(claude_after_un["hooks"]["SessionStart"][0]["hooks"][0]["command"], "python3 /some/other/hook.py")

        claude_md_after = (claude_dir / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("# Existing user guidelines", claude_md_after)
        self.assertNotIn("prolong:start", claude_md_after)

    def test_project_init_and_uninstall(self):
        project = self.home / "my-project"
        project.mkdir()

        init_project(project, clients=["claude-code"])
        status = check_project_status(project)
        self.assertTrue(status["installed"])
        self.assertTrue(status["gitignore_exists"])
        self.assertTrue(status["log_exists"])

        gitignore_content = (project / ".prolong" / ".gitignore").read_text(encoding="utf-8")
        self.assertEqual(gitignore_content, "*\n")

        uninstall_project(project, purge=False)
        # Log should be preserved
        self.assertTrue((project / ".prolong" / "log.jsonl").exists())

        uninstall_project(project, purge=True)
        # With purge, .prolong is removed
        self.assertFalse((project / ".prolong").exists())


if __name__ == "__main__":
    unittest.main()
