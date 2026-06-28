from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .collectors import collect_status
from .diagnostics import summarize_exit_code
from .renderers import render_json, render_markdown, render_text


CATEGORY_ALIASES = {
    "provider": "provider",
    "model": "provider",
    "plugin": "plugins",
    "plugins": "plugins",
    "mcp": "mcps",
    "mcps": "mcps",
    "skill": "skills",
    "skills": "skills",
    "agent": "agents",
    "agents": "agents",
    "hook": "hooks",
    "hooks": "hooks",
    "permission": "permissions",
    "permissions": "permissions",
    "diagnostic": "diagnostics",
    "diagnostics": "diagnostics",
    "diag": "diagnostics",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect Claude Code visible MCPs, skills, hooks, plugins, and provider settings for a project.",
    )
    parser.add_argument("--project", "-p", default=".", help="Project directory to inspect. Defaults to the current directory.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--markdown", action="store_true", help="Print Markdown tables.")
    parser.add_argument("--doctor", action="store_true", help="Run diagnostics and return non-zero when warnings/errors are found.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Include source paths, allowlists, and diagnostic hints.")
    parser.add_argument("--include-runtime", action="store_true", help="Run optional read-only runtime probes, such as localhost proxy /health.")
    parser.add_argument(
        "category",
        nargs="?",
        choices=sorted(CATEGORY_ALIASES),
        help="Show only one category: provider, plugin, mcp, skill, agent, hook, permission, or diagnostic.",
    )
    parser.add_argument("name", nargs="?", help="Show one item within the selected category, such as an MCP, hook, or skill name.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    category = CATEGORY_ALIASES.get(args.category) if args.category else None
    status = collect_status(
        Path(args.project),
        include_runtime=args.include_runtime,
        verbose=args.verbose,
        mcp_tool_name=args.name if category == "mcps" else None,
    )

    if args.name and not category:
        build_parser().error("name can only be used after a category, for example: ccd mcp playwright")

    if args.json:
        print(render_json(status, category=category, name=args.name))
    elif args.markdown:
        print(render_markdown(status, category=category, name=args.name))
    else:
        print(render_text(status, verbose=args.verbose or args.doctor or bool(category), category=category, name=args.name))

    if args.doctor:
        diagnostics = status.get("diagnostics", [])
        return summarize_exit_code_from_dicts(diagnostics)
    return 0


def summarize_exit_code_from_dicts(diagnostics: list[dict[str, object]]) -> int:
    from .models import Diagnostic

    return summarize_exit_code([
        Diagnostic(
            severity=str(item.get("severity", "info")),
            message=str(item.get("message", "")),
            source_file=str(item["source_file"]) if item.get("source_file") else None,
            hint=str(item["hint"]) if item.get("hint") else None,
        )
        for item in diagnostics
    ])


if __name__ == "__main__":
    sys.exit(main())
