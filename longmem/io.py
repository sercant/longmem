"""File system and IO helper functions."""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, content: str) -> None:
    """Replace a text file atomically while preserving file mode."""
    path.parent.mkdir(parents=True, exist_ok=True)
    old_mode: int | None = None
    try:
        old_mode = path.stat().st_mode & 0o777
    except FileNotFoundError:
        pass

    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if old_mode is not None:
            os.chmod(temporary_path, old_mode)
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def read_text(path: Path) -> str | None:
    """Read a text file, returning None if it does not exist."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def sha256(content: str) -> str:
    """Calculate the sha256 hash of a string."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def file_size(path: Path) -> int:
    """Return file size in bytes, or 0 if missing."""
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


def remove_path(path: Path, recursive: bool = False) -> None:
    """Remove a file or directory if it exists."""
    if not path.exists():
        return
    if path.is_dir():
        if recursive:
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.rmdir()
    else:
        path.unlink(missing_ok=True)


def remove_empty_parents(path: Path, stop_at: Path) -> None:
    """Remove empty parent directories up to stop_at."""
    stop_at = stop_at.resolve()
    current = path.resolve()
    while current != stop_at and current != current.parent:
        try:
            if not current.exists() or any(current.iterdir()):
                break
            current.rmdir()
        except OSError:
            break
        current = current.parent
