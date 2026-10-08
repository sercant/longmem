"""Utilities for managing markdown blocks with markers."""
from __future__ import annotations

import re

from longmem.constants import BLOCK_END, BLOCK_START

BLOCK_PATTERN = re.compile(
    rf"{re.escape(BLOCK_START)}[\s\S]*?{re.escape(BLOCK_END)}\n?",
    re.MULTILINE,
)


def has_managed_block(content: str | None) -> bool:
    """Return True if content contains the managed block."""
    if content is None:
        return False
    return bool(BLOCK_PATTERN.search(content))


def upsert_managed_block(content: str | None, block: str) -> str:
    """Insert or update the managed block in content."""
    if content is None or content.strip() == "":
        return f"{block}\n"
    if has_managed_block(content):
        updated = BLOCK_PATTERN.sub(f"{block}\n", content)
        return updated if updated.endswith("\n") else f"{updated}\n"
    return f"{content.rstrip()}\n\n{block}\n"


def remove_managed_block(content: str | None) -> str | None:
    """Remove the managed block from content, cleaning up whitespace."""
    if content is None or not has_managed_block(content):
        return content
    updated = BLOCK_PATTERN.sub("", content)
    updated = re.sub(r"\n{3,}", "\n\n", updated).rstrip()
    return f"{updated}\n" if updated else ""
