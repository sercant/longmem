"""Installer, uninstaller, and client adapter configurations for PRO-LONG."""
from __future__ import annotations

import json
import shlex
import shutil
from pathlib import Path
from typing import Any

from prolong.blocks import (
    has_managed_block,
    remove_managed_block,
    upsert_managed_block,
)
from prolong.constants import (
    CLAUDE_HOOK_EVENTS,
    CODEX_HOOK_EVENTS,
    INSTRUCTIONS_BLOCK,
    PACKAGE_VERSION,
    SUPPORTED_CLIENTS,
)
from prolong.io import atomic_write_text, file_size, read_text, remove_path


class ConfigurationError(ValueError):
    """Raised when configuration cannot be parsed or updated safely."""


def detect_clients(base_dir: Path | None = None) -> list[str]:
    """Detect available clients on system or in base_dir."""
    detected: list[str] = []
    base = base_dir or Path.home()

    # Check claude
    if shutil.which("claude") or (base / ".claude").is_dir():
        detected.append("claude-code")

    # Check codex
    if shutil.which("codex") or (base / ".codex").is_dir():
        detected.append("codex")

    return detected if detected else list(SUPPORTED_CLIENTS)


def normalize_clients(clients: list[str] | tuple[str, ...]) -> list[str]:
    """Validate and normalize client names."""
    if not isinstance(clients, (list, tuple)):
        raise ValueError("clients must be a list of supported client names")

    normalized: list[str] = []
    for raw in clients:
        c = raw.strip().lower()
        if c not in SUPPORTED_CLIENTS:
            supported = ", ".join(SUPPORTED_CLIENTS)
            raise ValueError(f"unsupported client {raw!r}; choose from {supported}")
        if c not in normalized:
            normalized.append(c)

    if not normalized:
        raise ValueError("at least one client is required")
    return normalized


def read_json_file(path: Path) -> dict[str, Any]:
    """Read a JSON object from file."""
    if not path.exists():
        return {}
    content = read_text(path)
    if content is None or not content.strip():
        return {}
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"configuration {path} is not valid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ConfigurationError(f"configuration {path} must contain a JSON object")
    return data


def write_json_file(path: Path, data: dict[str, Any]) -> None:
    """Write data as formatted JSON atomically."""
    atomic_write_text(path, json.dumps(data, indent=2) + "\n")


def is_prolong_handler(handler: Any, client: str) -> bool:
    """Check whether a hook handler is managed by prolong."""
    if not isinstance(handler, dict) or handler.get("type") != "command":
        return False

    command = str(handler.get("command") or "")
    args = handler.get("args")
    args_str = " ".join(str(a) for a in args) if isinstance(args, list) else ""
    full_cmd = f"{command} {args_str}".replace("\\", "/")

    return ("prolong/runtime.py" in full_cmd or ".prolong/runtime.py" in full_cmd) and (
        f"--hook {client}" in full_cmd or f"--prolong-hook {client}" in full_cmd or client in full_cmd
    )


def is_prolong_hook_group(group: Any, client: str) -> bool:
    """Check whether a hook group contains a prolong handler."""
    if not isinstance(group, dict):
        return False
    hooks = group.get("hooks")
    if not isinstance(hooks, list):
        return False
    return any(is_prolong_handler(h, client) for h in hooks)


def _install_client_hooks(
    config_path: Path,
    events: tuple[str, ...],
    client: str,
    handler_factory: Any,
) -> None:
    """Safely install hooks into a client configuration file without touching others."""
    config = read_json_file(config_path)
    hooks = config.get("hooks")
    if hooks is None or not isinstance(hooks, dict):
        hooks = {}
        config["hooks"] = hooks

    for event in events:
        raw_groups = hooks.get(event)
        groups = list(raw_groups) if isinstance(raw_groups, list) else []
        # Keep non-prolong groups
        filtered = [g for g in groups if not is_prolong_hook_group(g, client)]
        filtered.append({"hooks": [handler_factory(event)]})
        hooks[event] = filtered

    write_json_file(config_path, config)


def _uninstall_client_hooks(
    config_path: Path,
    events: tuple[str, ...],
    client: str,
) -> None:
    """Safely remove only prolong hooks from a client configuration file."""
    if not config_path.exists():
        return
    config = read_json_file(config_path)
    hooks = config.get("hooks")
    if not isinstance(hooks, dict):
        return

    for event in events:
        raw_groups = hooks.get(event)
        if not isinstance(raw_groups, list):
            continue
        filtered = [g for g in raw_groups if not is_prolong_hook_group(g, client)]
        if filtered:
            hooks[event] = filtered
        else:
            hooks.pop(event, None)

    if not hooks:
        config.pop("hooks", None)

    if not config:
        remove_path(config_path)
    else:
        write_json_file(config_path, config)


def update_managed_file(path: Path, block: str) -> None:
    """Update or add a managed block in a markdown or text file."""
    current = read_text(path)
    updated = upsert_managed_block(current, block)
    atomic_write_text(path, updated)


def remove_managed_file_block(path: Path) -> None:
    """Remove a managed block from a file. If file becomes empty, delete it."""
    if not path.exists():
        return
    current = read_text(path)
    updated = remove_managed_block(current)
    if updated is None:
        return
    if not updated.strip():
        remove_path(path)
    else:
        atomic_write_text(path, updated)


def _template_path(name: str) -> Path:
    """Get the path to a template file."""
    return Path(__file__).resolve().parent / "templates" / name


def _copy_skill_templates(dest_dir: Path) -> None:
    """Copy skill markdown and openai metadata into dest_dir."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_template_path("SKILL.md"), dest_dir / "SKILL.md")
    agents_dir = dest_dir / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_template_path("agents/openai.yaml"), agents_dir / "openai.yaml")


# --- Claude Code adapter ---

def install_claude_hooks(base_dir: Path, runtime_path: str) -> None:
    """Install Claude Code lifecycle hooks."""
    config_path = base_dir / ".claude" / "settings.json"

    def make_handler(event_name: str) -> dict[str, Any]:
        return {
            "type": "command",
            "command": "python3",
            "args": [runtime_path, "--hook", "claude-code"],
            "timeout": 3,
        }

    _install_client_hooks(config_path, CLAUDE_HOOK_EVENTS, "claude-code", make_handler)


def uninstall_claude_hooks(base_dir: Path) -> None:
    """Uninstall Claude Code hooks."""
    config_path = base_dir / ".claude" / "settings.json"
    _uninstall_client_hooks(config_path, CLAUDE_HOOK_EVENTS, "claude-code")


# --- Codex adapter ---

def install_codex_hooks(base_dir: Path, runtime_path: str) -> None:
    """Install Codex lifecycle hooks."""
    config_path = base_dir / ".codex" / "hooks.json"

    def make_handler(event_name: str) -> dict[str, Any]:
        cmd_unix = f"python3 {shlex.quote(runtime_path)} --hook codex"
        win_runtime = runtime_path.replace("/", "\\")
        cmd_win = f'python "{win_runtime}" --hook codex'
        return {
            "type": "command",
            "command": cmd_unix,
            "commandWindows": cmd_win,
            "timeout": 3,
        }

    _install_client_hooks(config_path, CODEX_HOOK_EVENTS, "codex", make_handler)


def uninstall_codex_hooks(base_dir: Path) -> None:
    """Uninstall Codex hooks."""
    config_path = base_dir / ".codex" / "hooks.json"
    _uninstall_client_hooks(config_path, CODEX_HOOK_EVENTS, "codex")


# --- Global Init / Status / Uninstall ---

def init_global(
    clients: list[str] | None = None,
    home: Path | None = None,
) -> dict[str, Any]:
    """Initialize PRO-LONG globally for all repositories."""
    user_home = (home or Path.home()).resolve()
    target_clients = normalize_clients(clients if clients is not None else detect_clients(user_home))

    # 1. Install global runtime script
    runtime_dest = user_home / ".prolong" / "runtime.py"
    runtime_dest.parent.mkdir(parents=True, exist_ok=True)
    src_runtime = Path(__file__).resolve().parent / "runtime.py"
    shutil.copy2(src_runtime, runtime_dest)
    runtime_dest.chmod(0o755)

    # 2. Install global skills
    agents_skill_dir = user_home / ".agents" / "skills" / "prolong"
    _copy_skill_templates(agents_skill_dir)

    claude_skill_dir = user_home / ".claude" / "skills" / "prolong"
    _copy_skill_templates(claude_skill_dir)

    codex_skill_dir = user_home / ".codex" / "skills" / "prolong"
    _copy_skill_templates(codex_skill_dir)

    # 3. Client hooks & instructions
    installed_clients: list[str] = []

    if "claude-code" in target_clients:
        install_claude_hooks(user_home, str(runtime_dest))
        update_managed_file(user_home / ".claude" / "CLAUDE.md", INSTRUCTIONS_BLOCK)
        installed_clients.append("claude-code")
    else:
        uninstall_claude_hooks(user_home)
        remove_managed_file_block(user_home / ".claude" / "CLAUDE.md")

    if "codex" in target_clients:
        install_codex_hooks(user_home, str(runtime_dest))
        update_managed_file(user_home / ".codex" / "AGENTS.md", INSTRUCTIONS_BLOCK)
        if (user_home / ".agents").is_dir() or (user_home / ".agents" / "AGENTS.md").exists():
            update_managed_file(user_home / ".agents" / "AGENTS.md", INSTRUCTIONS_BLOCK)
        installed_clients.append("codex")
    else:
        uninstall_codex_hooks(user_home)
        remove_managed_file_block(user_home / ".codex" / "AGENTS.md")
        remove_managed_file_block(user_home / ".agents" / "AGENTS.md")

    # 4. Manifest
    manifest = {
        "version": PACKAGE_VERSION,
        "scope": "global",
        "clients": installed_clients,
        "runtime": str(runtime_dest),
        "skills": [
            str(agents_skill_dir / "SKILL.md"),
            str(claude_skill_dir / "SKILL.md"),
            str(codex_skill_dir / "SKILL.md"),
        ],
    }
    write_json_file(user_home / ".prolong" / "install.json", manifest)
    return manifest


def uninstall_global(home: Path | None = None, purge: bool = False) -> None:
    """Uninstall PRO-LONG globally."""
    user_home = (home or Path.home()).resolve()

    uninstall_claude_hooks(user_home)
    remove_managed_file_block(user_home / ".claude" / "CLAUDE.md")

    uninstall_codex_hooks(user_home)
    remove_managed_file_block(user_home / ".codex" / "AGENTS.md")
    remove_managed_file_block(user_home / ".agents" / "AGENTS.md")

    for skill_dir in (
        user_home / ".agents" / "skills" / "prolong",
        user_home / ".claude" / "skills" / "prolong",
        user_home / ".codex" / "skills" / "prolong",
    ):
        if skill_dir.exists():
            shutil.rmtree(skill_dir, ignore_errors=True)

    (user_home / ".prolong" / "runtime.py").unlink(missing_ok=True)
    (user_home / ".prolong" / "install.json").unlink(missing_ok=True)

    if purge:
        shutil.rmtree(user_home / ".prolong", ignore_errors=True)


deinit_global = uninstall_global


def check_global_status(home: Path | None = None) -> dict[str, Any]:
    """Check global PRO-LONG status."""
    user_home = (home or Path.home()).resolve()
    manifest_path = user_home / ".prolong" / "install.json"
    runtime_path = user_home / ".prolong" / "runtime.py"

    has_manifest = manifest_path.exists()
    runtime_exists = runtime_path.exists()
    agents_skill_exists = (user_home / ".agents" / "skills" / "prolong" / "SKILL.md").exists()
    claude_skill_exists = (user_home / ".claude" / "skills" / "prolong" / "SKILL.md").exists()

    claude_settings = read_json_file(user_home / ".claude" / "settings.json")
    claude_hooks = claude_settings.get("hooks", {})
    claude_installed = all(
        isinstance(claude_hooks.get(ev), list)
        and any(is_prolong_hook_group(g, "claude-code") for g in claude_hooks[ev])
        for ev in CLAUDE_HOOK_EVENTS
    )

    codex_config = read_json_file(user_home / ".codex" / "hooks.json")
    codex_hooks = codex_config.get("hooks", {})
    codex_installed = all(
        isinstance(codex_hooks.get(ev), list)
        and any(is_prolong_hook_group(g, "codex") for g in codex_hooks[ev])
        for ev in CODEX_HOOK_EVENTS
    )

    installed = runtime_exists and (claude_installed or codex_installed)

    return {
        "installed": installed,
        "has_manifest": has_manifest,
        "runtime_exists": runtime_exists,
        "runtime_path": str(runtime_path),
        "skills": {
            "agents": agents_skill_exists,
            "claude": claude_skill_exists,
        },
        "claude_code": {
            "installed": claude_installed,
            "has_claude_md": has_managed_block(read_text(user_home / ".claude" / "CLAUDE.md")),
        },
        "codex": {
            "installed": codex_installed,
            "has_agents_md": has_managed_block(read_text(user_home / ".codex" / "AGENTS.md")),
        },
    }


# --- Project-Local Init / Status / Uninstall ---

def init_project(
    root: Path,
    clients: list[str] | None = None,
) -> dict[str, Any]:
    """Initialize PRO-LONG in a specific project."""
    project_root = root.resolve()
    target_clients = normalize_clients(clients if clients is not None else detect_clients(project_root))

    # 1. Initialize .prolong folder and .gitignore
    prolong_dir = project_root / ".prolong"
    prolong_dir.mkdir(parents=True, exist_ok=True)
    gitignore = prolong_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n", encoding="utf-8")
    log_file = prolong_dir / "log.jsonl"
    if not log_file.exists():
        log_file.touch()

    # 2. Runtime script
    runtime_dest = prolong_dir / "runtime.py"
    src_runtime = Path(__file__).resolve().parent / "runtime.py"
    shutil.copy2(src_runtime, runtime_dest)
    runtime_dest.chmod(0o755)

    # 3. Project skills
    skill_dir = project_root / ".agents" / "skills" / "prolong"
    _copy_skill_templates(skill_dir)

    # 4. Client hooks & instructions
    installed_clients: list[str] = []

    if "claude-code" in target_clients:
        install_claude_hooks(project_root, "${CLAUDE_PROJECT_DIR}/.prolong/runtime.py")
        update_managed_file(project_root / "CLAUDE.md", INSTRUCTIONS_BLOCK)
        installed_clients.append("claude-code")

    if "codex" in target_clients:
        install_codex_hooks(
            project_root,
            '$(git rev-parse --show-toplevel 2>/dev/null || pwd)/.prolong/runtime.py',
        )
        update_managed_file(project_root / "AGENTS.md", INSTRUCTIONS_BLOCK)
        installed_clients.append("codex")

    # 5. Manifest
    manifest = {
        "version": PACKAGE_VERSION,
        "scope": "project",
        "clients": installed_clients,
        "runtime": ".prolong/runtime.py",
        "log": ".prolong/log.jsonl",
        "skill": ".agents/skills/prolong/SKILL.md",
    }
    write_json_file(prolong_dir / "install.json", manifest)
    return manifest


def uninstall_project(root: Path, purge: bool = False) -> None:
    """Uninstall PRO-LONG from a project."""
    project_root = root.resolve()

    uninstall_claude_hooks(project_root)
    remove_managed_file_block(project_root / "CLAUDE.md")

    uninstall_codex_hooks(project_root)
    remove_managed_file_block(project_root / "AGENTS.md")

    skill_dir = project_root / ".agents" / "skills" / "prolong"
    if skill_dir.exists():
        shutil.rmtree(skill_dir, ignore_errors=True)

    prolong_dir = project_root / ".prolong"
    (prolong_dir / "runtime.py").unlink(missing_ok=True)
    (prolong_dir / "install.json").unlink(missing_ok=True)

    if purge:
        shutil.rmtree(prolong_dir, ignore_errors=True)


deinit_project = uninstall_project


def check_project_status(root: Path) -> dict[str, Any]:
    """Check status of PRO-LONG in a project."""
    project_root = root.resolve()
    prolong_dir = project_root / ".prolong"
    manifest_path = prolong_dir / "install.json"
    runtime_path = prolong_dir / "runtime.py"
    log_path = prolong_dir / "log.jsonl"
    gitignore_path = prolong_dir / ".gitignore"
    skill_path = project_root / ".agents" / "skills" / "prolong" / "SKILL.md"

    has_manifest = manifest_path.exists()
    runtime_exists = runtime_path.exists()
    log_exists = log_path.exists()
    gitignore_exists = gitignore_path.exists()
    skill_exists = skill_path.exists()

    claude_settings = read_json_file(project_root / ".claude" / "settings.json")
    claude_hooks = claude_settings.get("hooks", {})
    claude_installed = all(
        isinstance(claude_hooks.get(ev), list)
        and any(is_prolong_hook_group(g, "claude-code") for g in claude_hooks[ev])
        for ev in CLAUDE_HOOK_EVENTS
    )

    codex_config = read_json_file(project_root / ".codex" / "hooks.json")
    codex_hooks = codex_config.get("hooks", {})
    codex_installed = all(
        isinstance(codex_hooks.get(ev), list)
        and any(is_prolong_hook_group(g, "codex") for g in codex_hooks[ev])
        for ev in CODEX_HOOK_EVENTS
    )

    global_status = check_global_status()

    installed = has_manifest and runtime_exists and (claude_installed or codex_installed)

    return {
        "project": str(project_root),
        "installed": installed,
        "global_active": global_status["installed"],
        "runtime_exists": runtime_exists,
        "log_exists": log_exists,
        "log_bytes": file_size(log_path),
        "gitignore_exists": gitignore_exists,
        "skill_exists": skill_exists,
        "claude_code": {
            "installed": claude_installed,
            "has_claude_md": has_managed_block(read_text(project_root / "CLAUDE.md")),
        },
        "codex": {
            "installed": codex_installed,
            "has_agents_md": has_managed_block(read_text(project_root / "AGENTS.md")),
        },
    }
