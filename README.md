# PRO-LONG (Python Edition)

**Durable, programmatic memory for coding agents.**

Long tasks outlive context windows. After compaction or a fresh session, coding agents lose earlier decisions, repeat failed work, and miss important tool outputs.

PRO-LONG records coding-session events in a local, append-only JSONL log (`.prolong/log.jsonl`) and equips the agent with a skill for searching only the history it needs.

Works natively with **Claude Code** and **Codex**. Pure Python 3 (standard library only) with zero external dependencies.

---

## Key Features

- **Zero Dependencies**: Pure Python 3 standard library. No npm, no node, no heavy frameworks.
- **Global & Local Workflows**:
  - **Global Mode** (`prolong init --global`): Installs once into `~/.claude/` and `~/.codex/`. Every git repository or workspace automatically initializes its own isolated memory on session start.
  - **Local Mode** (`prolong init`): Explicitly initializes a single project repository.
- **Automatic Gitignore**: On `SessionStart`, PRO-LONG initializes `.prolong/` at the root of the git repository and creates `.prolong/.gitignore` with `*` so all memory logs remain untracked by Git automatically.
- **Safe Coexistence**: Preserves existing hook configurations (such as `proshort`, `rtk`, or custom user hooks) and existing instructions in `CLAUDE.md` and `AGENTS.md`.
- **Anti-Recursion / Self-Read Filtering**: Reads of `.prolong/log.jsonl` are automatically excluded from recording, preventing memory queries from duplicating into the log.

---

## Quick Start

### 1. Run directly with uvx (Zero Installation)

From the `pro-long-2` directory:

```bash
cd /path/to/pro-long-2
uvx . --version
```

`uvx` builds `prolong` in an isolated environment and runs it without requiring manual installation. Prefix any command with `uvx .`:

```bash
# Initialize globally
uvx . init --global

# Check global status
uvx . status --global
```

Or run from any directory:

```bash
uvx --from /path/to/pro-long-2 prolong init --global
```

### 2. Or Install with uv / pip

```bash
# Install as a global CLI tool via uv
uv tool install --editable /path/to/pro-long-2

# Or install in active virtualenv
pip install -e /path/to/pro-long-2
```

After installation, run commands directly:

```bash
prolong init --global
prolong status --global
```

This:
1. Copies the standalone runtime to `~/.prolong/runtime.py`.
2. Registers lifecycle hooks in `~/.claude/settings.json` and `~/.codex/hooks.json`.
3. Injects retrieval instructions into `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md` (and `~/.agents/AGENTS.md`).
4. Installs the `prolong` skill into `~/.claude/skills/prolong/` and `~/.agents/skills/prolong/`.

### 3. Initialize Per-Project (Optional)

To initialize memory in only a specific project directory:

```bash
cd /path/to/project
prolong init
```

---

## How It Works

```mermaid
flowchart LR
    Agent["Coding Agent (Claude Code / Codex)"] -->|"Lifecycle hooks (SessionStart, Prompt, Tool, Stop)"| Runtime["~/.prolong/runtime.py"]
    Runtime -->|"Find git root & ensure .gitignore (*)"| Log[".prolong/log.jsonl"]
    Log -->|"Agent retrieves via rg / jq / grep"| Agent
```

1. When a session begins, the `SessionStart` hook fires.
2. `runtime.py` resolves the git repository root (`git rev-parse --show-toplevel`).
3. It creates `<repo_root>/.prolong/` with `.gitignore` containing `*` and creates `log.jsonl`.
4. Subsequent prompts, tool executions, and assistant messages are recorded as JSON lines.
5. When prior context is needed, the agent searches `.prolong/log.jsonl` using normal shell tools (`rg`, `grep`, `jq`, Python) without loading whole transcripts into model context.

### Log Format

Each line in `.prolong/log.jsonl` is a self-contained JSON object:

```json
{
  "timestamp": "2026-09-16T02:23:00.123456Z",
  "client": "claude-code",
  "sessionId": "sess-abc123",
  "type": "user_prompt",
  "content": {
    "hook_event_name": "UserPromptSubmit",
    "prompt": "Migrate database schema to v2"
  }
}
```

Canonical event types:
- `session_start`
- `session_end`
- `user_prompt`
- `tool_call`
- `tool_result`
- `assistant_message`

---

## Retrieving History

The agent skill teaches models to search the log narrowly:

```bash
# Find when a file or decision was mentioned
rg -n 'migration|schema|failed' .prolong/log.jsonl

# Review recent session entries
tail -n 50 .prolong/log.jsonl

# Filter for tool execution results
jq -c 'select(.type == "tool_result")' .prolong/log.jsonl | tail -n 20
```

---

## CLI Reference

### `init`
```bash
# Global install (all repos)
prolong init --global

# Specify clients explicitly
prolong init --global --client claude-code,codex

# Local project install
prolong init --dir /path/to/project
```

### `status`
```bash
# Check global installation status
prolong status --global

# Check current project status
prolong status

# Output machine-readable JSON
prolong status --json
```

### `deinit` (alias: `uninstall`)
```bash
# Deinitialize globally (preserves logs)
uvx . deinit --global
# or: prolong deinit --global

# Deinitialize globally and purge ~/.prolong
uvx . deinit --global --purge

# Deinitialize from a specific project
uvx . deinit --dir /path/to/project [--purge]
```

---

## Running Tests

Run the test suite with Python's built-in `unittest`:

```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

---

## License

MIT
