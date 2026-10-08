"""Unit tests for block management."""
import unittest

from prolong.blocks import (
    has_managed_block,
    remove_managed_block,
    upsert_managed_block,
)
from prolong.constants import INSTRUCTIONS_BLOCK


class TestBlocks(unittest.TestCase):
    def test_has_managed_block(self):
        self.assertFalse(has_managed_block(None))
        self.assertFalse(has_managed_block(""))
        self.assertFalse(has_managed_block("# User rules\nSome content\n"))
        self.assertTrue(has_managed_block(f"# User rules\n{INSTRUCTIONS_BLOCK}\nMore rules\n"))

    def test_upsert_managed_block_empty(self):
        result = upsert_managed_block("", INSTRUCTIONS_BLOCK)
        self.assertEqual(result, f"{INSTRUCTIONS_BLOCK}\n")

    def test_upsert_managed_block_append(self):
        original = "# Existing rules\nLine 1\n"
        result = upsert_managed_block(original, INSTRUCTIONS_BLOCK)
        self.assertTrue(result.startswith("# Existing rules\nLine 1\n\n"))
        self.assertTrue(result.endswith(f"{INSTRUCTIONS_BLOCK}\n"))
        self.assertTrue(has_managed_block(result))

    def test_upsert_managed_block_replace(self):
        first = upsert_managed_block("# Header\n", INSTRUCTIONS_BLOCK)
        custom_block = "<!-- prolong:start -->\n## New content\n<!-- prolong:end -->"
        second = upsert_managed_block(first, custom_block)
        self.assertIn("## New content", second)
        self.assertNotIn("PRO-LONG maintains a local", second)
        self.assertTrue(second.startswith("# Header\n\n"))

    def test_remove_managed_block(self):
        original = "# Header\n\n- rule 1\n- rule 2\n"
        with_block = upsert_managed_block(original, INSTRUCTIONS_BLOCK)
        removed = remove_managed_block(with_block)
        self.assertEqual(removed, original)

    def test_remove_managed_block_when_only_block(self):
        with_block = upsert_managed_block("", INSTRUCTIONS_BLOCK)
        removed = remove_managed_block(with_block)
        self.assertEqual(removed, "")


if __name__ == "__main__":
    unittest.main()
