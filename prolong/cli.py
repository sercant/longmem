"""Command line interface for PRO-LONG."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from prolong import __version__
from prolong.installer import (
    check_global_status,
    check_project_status,
    init_global,
    init_project,
    normalize_clients,
    uninstall_global,
    uninstall_project,
)


def cmd_init(args: argparse.Namespace) -> int:
    """Handle prolong init."""
    raw_clients = args.client.split(",") if args.client is not None else None
    clients = normalize_clients(raw_clients) if raw_clients else None

    if args.is_global:
        manifest = init_global(clients=clients)
        print("PRO-LONG initialized globally:")
        print(f"  Clients:     {', '.join(manifest['clients'])}")
        print(f"  Runtime:     {manifest['runtime']}")
        print("  Skills:      ~/.claude/skills/prolong, ~/.agents/skills/prolong, ~/.codex/skills/prolong")
        print("  Pointers:    ~/.claude/CLAUDE.md, ~/.codex/AGENTS.md")
        print("  Workspaces:  Automatically initializes <git_root>/.prolong on SessionStart")
        return 0

    root = Path(args.dir).resolve()
    manifest = init_project(root, clients=clients)
    print(f"PRO-LONG initialized in {root}:")
    print(f"  Clients:     {', '.join(manifest['clients'])}")
    print(f"  Runtime:     {manifest['runtime']}")
    print(f"  Log:         {manifest['log']}")
    print("  Gitignore:   .prolong/.gitignore (*)")
    print(f"  Skill:       {manifest['skill']}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Handle prolong status."""
    if args.is_global:
        status = check_global_status()
        if args.json:
            print(json.dumps(status, indent=2))
            return 0 if status["installed"] else 1

        print("PRO-LONG Global Status:")
        print(f"  Installed:       {'yes' if status['installed'] else 'no'}")
        print(f"  Runtime:         {'yes' if status['runtime_exists'] else 'no'} ({status['runtime_path']})")
        print(f"  Skills:          agents={'yes' if status['skills']['agents'] else 'no'}, claude={'yes' if status['skills']['claude'] else 'no'}")
        print("  Clients:")
        print(f"    claude-code:   {'active' if status['claude_code']['installed'] else 'not installed'} (CLAUDE.md={'yes' if status['claude_code']['has_claude_md'] else 'no'})")
        print(f"    codex:         {'active' if status['codex']['installed'] else 'not installed'} (AGENTS.md={'yes' if status['codex']['has_agents_md'] else 'no'})")
        return 0 if status["installed"] else 1

    root = Path(args.dir).resolve()
    status = check_project_status(root)
    if args.json:
        print(json.dumps(status, indent=2))
        return 0 if (status["installed"] or status["global_active"]) else 1

    print(f"PRO-LONG Status for {root}:")
    print(f"  Project Installed:  {'yes' if status['installed'] else 'no'}")
    if status["global_active"]:
        print("  Global Active:      yes (SessionStart auto-initializes repository history)")
    print(f"  Runtime:            {'yes' if status['runtime_exists'] else 'no'}")
    print(f"  Log:                {'yes' if status['log_exists'] else 'no'} ({status['log_bytes']} bytes)")
    print(f"  Gitignore:          {'yes' if status['gitignore_exists'] else 'no'}")
    print(f"  Skill:              {'yes' if status['skill_exists'] else 'no'}")
    print("  Clients:")
    print(f"    claude-code:      {'active' if status['claude_code']['installed'] else 'not installed'}")
    print(f"    codex:            {'active' if status['codex']['installed'] else 'not installed'}")
    return 0 if (status["installed"] or status["global_active"]) else 1


def cmd_deinit(args: argparse.Namespace) -> int:
    """Handle prolong deinit / uninstall."""
    if args.is_global:
        uninstall_global(purge=args.purge)
        msg = " (purged ~/.prolong)" if args.purge else " (preserved ~/.prolong logs)"
        print(f"PRO-LONG deinitialized globally{msg}.")
        return 0

    root = Path(args.dir).resolve()
    uninstall_project(root, purge=args.purge)
    msg = " (purged .prolong)" if args.purge else " (preserved .prolong logs)"
    print(f"PRO-LONG deinitialized from {root}{msg}.")
    return 0


cmd_uninstall = cmd_deinit


def build_parser() -> argparse.ArgumentParser:
    """Construct argument parser."""
    parser = argparse.ArgumentParser(
        prog="prolong",
        description="PRO-LONG: Durable programmatic memory for coding agents.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    init_parser = subparsers.add_parser("init", help="Initialize PRO-LONG in project or globally")
    init_parser.add_argument("--global", dest="is_global", action="store_true", help="Install globally")
    init_parser.add_argument("--dir", default=".", help="Project directory (default: current)")
    init_parser.add_argument("--client", help="Comma-separated client list (claude-code, codex)")
    init_parser.set_defaults(func=cmd_init)

    # status
    status_parser = subparsers.add_parser("status", help="Check PRO-LONG status")
    status_parser.add_argument("--global", dest="is_global", action="store_true", help="Check global status")
    status_parser.add_argument("--dir", default=".", help="Project directory (default: current)")
    status_parser.add_argument("--json", action="store_true", help="Output JSON format")
    status_parser.set_defaults(func=cmd_status)

    # deinit (with alias uninstall)
    deinit_parser = subparsers.add_parser(
        "deinit",
        aliases=["uninstall"],
        help="Deinitialize PRO-LONG in project or globally",
    )
    deinit_parser.add_argument("--global", dest="is_global", action="store_true", help="Deinitialize globally")
    deinit_parser.add_argument("--dir", default=".", help="Project directory (default: current)")
    deinit_parser.add_argument("--purge", action="store_true", help="Delete history logs as well")
    deinit_parser.set_defaults(func=cmd_deinit)

    return parser


def main(argv: list[str] | None = None) -> None:
    """Main CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)
    code = args.func(args)
    sys.exit(code)


if __name__ == "__main__":
    main()
