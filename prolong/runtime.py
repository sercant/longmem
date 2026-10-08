#!/usr/bin/env python3
"""PRO-LONG runtime: logs coding session events into local append-only JSONL memory."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore


def resolve_workspace_root(
    candidate: Path | str | None = None,
    event: Mapping[str, Any] | None = None,
) -> Path:
    """Resolve the git repo or workspace root for the current session.

    Resolution strategy:
    1. Check candidate if provided.
    2. Check event payload (cwd, workspace, project_dir, projectDir).
    3. Check environment variables (CLAUDE_PROJECT_DIR, CODEX_WORKSPACE_DIR, CODEX_PROJECT_DIR).
    4. Fall back to current working directory (os.getcwd()).
    5. Run `git rev-parse --show-toplevel` (handles both regular git repos and git worktrees).
    6. Fallback: walk directory parents searching for .git directory or file.
    7. If not in a git repo, return the candidate directory.
    """
    start: Path | None = None
    if candidate:
        start = Path(candidate)
    elif event:
        cwd_val = (
            event.get("cwd")
            or event.get("workspace")
            or event.get("project_dir")
            or event.get("projectDir")
        )
        if cwd_val:
            start = Path(str(cwd_val))

    if not start:
        env_dir = (
            os.environ.get("CLAUDE_PROJECT_DIR")
            or os.environ.get("CODEX_WORKSPACE_DIR")
            or os.environ.get("CODEX_PROJECT_DIR")
        )
        if env_dir:
            start = Path(env_dir)
        else:
            start = Path.cwd()

    start = start.resolve()
    if start.is_file():
        start = start.parent

    # 1. Attempt git rev-parse --show-toplevel (works for both standard repos and worktrees)
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(start),
            capture_output=True,
            text=True,
            timeout=2,
        )
        if res.returncode == 0 and res.stdout.strip():
            return Path(res.stdout.strip()).resolve()
    except Exception:
        pass

    # 2. Fallback: walk up looking for .git (file for worktree or dir for standard repo)
    for p in [start, *start.parents]:
        if (p / ".git").exists():
            return p.resolve()

    # 3. Plain directory fallback
    return start


def init_prolong_dir(root: Path) -> Path:
    """Ensure <root>/.prolong exists with a .gitignore containing '*'."""
    prolong_dir = root.resolve() / ".prolong"
    prolong_dir.mkdir(parents=True, exist_ok=True)

    gitignore_file = prolong_dir / ".gitignore"
    if not gitignore_file.exists():
        gitignore_file.write_text("*\n", encoding="utf-8")

    log_file = prolong_dir / "log.jsonl"
    if not log_file.exists():
        log_file.touch()

    return prolong_dir


def event_type(event: Mapping[str, Any]) -> str:
    """Map client hook event names to canonical PRO-LONG event types."""
    name = str(event.get("hook_event_name") or event.get("type") or "event")
    lower = name.lower()
    if "session" in lower and ("start" in lower or "created" in lower):
        return "session_start"
    if "session" in lower and ("end" in lower or "shutdown" in lower or "idle" in lower):
        return "session_end"
    if "prompt" in lower or (
        "message" in lower
        and isinstance(event.get("message"), dict)
        and event["message"].get("role") == "user"
    ):
        return "user_prompt"
    if "tool" in lower and (
        "result" in lower
        or "after" in lower
        or "end" in lower
        or "post" in lower
        or "failure" in lower
    ):
        return "tool_result"
    if "tool" in lower:
        return "tool_call"
    if "stop" in lower or (
        "message" in lower
        and isinstance(event.get("message"), dict)
        and event["message"].get("role") == "assistant"
    ):
        return "assistant_message"
    return name


def is_self_read(payload: Any) -> bool:
    """Detect if a tool call/result is reading or searching .prolong/log.jsonl."""
    if payload is None:
        return False
    try:
        serialized = json.dumps(payload)
    except Exception:
        serialized = str(payload)
    return ".prolong/log.jsonl" in serialized


def default_json_serializer(obj: Any) -> Any:
    """Handle objects not serializable by default json encoder."""
    if isinstance(obj, (set, frozenset)):
        return list(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


def record(
    client: str,
    event: Mapping[str, Any],
    root: Path | None = None,
) -> None:
    """Record an event into the project's .prolong/log.jsonl."""
    t = event_type(event)

    # Filter out self-reads to prevent memory feedback loops
    if t in ("tool_call", "tool_result"):
        tool_input = (
            event.get("tool_input")
            or event.get("toolInput")
            or event.get("args")
            or event.get("input")
            or event.get("command")
        )
        if is_self_read(tool_input):
            return

    repo_root = root or resolve_workspace_root(event=event)
    prolong_dir = init_prolong_dir(repo_root)
    log_file = prolong_dir / "log.jsonl"

    session_id = (
        event.get("session_id")
        or event.get("sessionID")
        or event.get("sessionId")
    )
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "client": client,
        "sessionId": session_id,
        "type": t,
        "content": dict(event),
    }

    line = json.dumps(entry, default=default_json_serializer, ensure_ascii=False) + "\n"

    # Concurrency-safe append with flock
    with open(log_file, "a", encoding="utf-8") as f:
        if fcntl is not None:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                f.write(line)
                f.flush()
            finally:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
        else:
            f.write(line)
            f.flush()


def parse_client_arg(argv: list[str]) -> str:
    """Extract client name from command line arguments."""
    client = "unknown"
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--hook", "--prolong-hook", "-c", "--client"):
            if i + 1 < len(argv):
                client = argv[i + 1]
                break
        elif not arg.startswith("-") and i > 0:
            client = arg
        i += 1
    return client


def main() -> None:
    """Main CLI hook receiver reading JSON from stdin."""
    client = parse_client_arg(sys.argv[1:])

    raw_input = ""
    try:
        if not sys.stdin.isatty():
            raw_input = sys.stdin.read()
    except Exception:
        raw_input = ""

    payload: dict[str, Any] = {}
    if raw_input.strip():
        try:
            parsed = json.loads(raw_input)
            if isinstance(parsed, dict):
                payload = parsed
        except Exception:
            payload = {"raw": raw_input}

    try:
        record(client, payload)
    except Exception as exc:
        sys.stderr.write(f"PRO-LONG hook warning: {exc}\n")

    sys.stdout.write("{}\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
