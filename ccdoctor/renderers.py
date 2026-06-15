from __future__ import annotations

import json
import os
from typing import Any


COLORS = {
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "reset": "\033[0m",
}


SECTION_ICONS = {
    "Provider / Model": "🧠",
    "Plugins": "🔌",
    "MCPs": "🧰",
    "Skills": "✨",
    "Agents": "🤖",
    "Hooks": "🪝",
    "Permissions": "🔐",
    "Diagnostics": "🩺",
}


SECTION_PAIRS = (
    ("Plugins", "plugins"),
    ("MCPs", "mcps"),
    ("Skills", "skills"),
    ("Agents", "agents"),
    ("Hooks", "hooks"),
    ("Permissions", "permissions"),
)


def render_json(status: dict[str, Any], category: str | None = None, name: str | None = None) -> str:
    if category:
        status = filter_status(status, category, name=name)
    return json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True)


def render_text(status: dict[str, Any], verbose: bool = False, category: str | None = None, name: str | None = None) -> str:
    lines: list[str] = []
    lines.append(color("✨ Claude Code Doctor", "bold", "cyan"))
    lines.append(f"📁 {color('Project:', 'bold')} {status['project_root']}")
    lines.append("")

    if category in {None, "provider"}:
        append_provider(lines, status)

    for title, key in SECTION_PAIRS:
        if category not in {None, key}:
            continue
        lines.append(format_section(title))
        items = matching_items(status.get(key, []), name)
        if not items:
            missing = f" named {name!r}" if name else ""
            lines.append(f"  {color('◦ none detected' + missing, 'dim')}")
        for item in items:
            if name:
                append_item_detail(lines, item)
            else:
                lines.append(format_item(item, verbose=verbose))
        lines.append("")

    if category in {None, "diagnostics"}:
        append_diagnostics(lines, status, verbose=verbose, name=name)
    return "\n".join(lines)


def append_provider(lines: list[str], status: dict[str, Any]) -> None:
    provider_settings = status.get("provider", {}).get("settings", [])
    lines.append(format_section("Provider / Model"))
    if provider_settings:
        first = provider_settings[0]
        if "model" in first:
            lines.append(f"  • 🧠 {color('model:', 'bold')} {first['model']}")
        env = first.get("env", {}) if isinstance(first, dict) else {}
        if isinstance(env, dict):
            for key in sorted(env):
                lines.append(f"  • 🌱 {color(key + ':', 'bold')} {env[key]}")
        if "statusLine" in first:
            status_line = first["statusLine"]
            command = status_line.get("command") if isinstance(status_line, dict) else status_line
            lines.append(f"  • 📊 {color('statusline:', 'bold')} {command}")
    else:
        lines.append(f"  {color('◦ no provider settings detected', 'dim')}")
    runtime_probe = status.get("provider", {}).get("runtime_probe")
    if runtime_probe:
        ok = bool(runtime_probe.get("ok"))
        label = color("ok", "green") if ok else color("failed", "red")
        icon = "✅" if ok else "❌"
        lines.append(f"  • {icon} {color('runtime probe:', 'bold')} {label} {runtime_probe.get('health_url', '')}")
    lines.append("")


def append_diagnostics(lines: list[str], status: dict[str, Any], verbose: bool = False, name: str | None = None) -> None:
    lines.append(format_section("Diagnostics"))
    diagnostics = matching_diagnostics(status.get("diagnostics", []), name)
    if not diagnostics:
        missing = f" matching {name!r}" if name else ""
        lines.append(f"  ✅ {color('OK:', 'green', 'bold')} no warnings or errors{missing}")
    for diagnostic in diagnostics:
        severity = str(diagnostic.get("severity", "info")).upper()
        source = f" ({diagnostic['source_file']})" if diagnostic.get("source_file") else ""
        lines.append(f"  {severity_icon(severity)} {format_severity(severity)}: {diagnostic.get('message', '')}{source}")
        if verbose and diagnostic.get("hint"):
            lines.append(f"    💡 {color('hint:', 'yellow')} {diagnostic['hint']}")


def append_item_detail(lines: list[str], item: dict[str, Any]) -> None:
    lines.append(format_item(item, verbose=True))
    for key in ("kind", "name", "scope", "provider", "effective", "managed_by", "source_file"):
        value = item.get(key)
        if value is not None:
            lines.append(f"    {color(key + ':', 'bold')} {value}")
    metadata = item.get("metadata", {})
    if isinstance(metadata, dict) and metadata:
        lines.append(f"    {color('metadata:', 'bold')}")
        for key, value in metadata.items():
            if value in (None, "", [], {}):
                continue
            lines.extend(format_nested_value(value, indent=6, label=str(key)))
    diagnostics = item.get("diagnostics", [])
    if diagnostics:
        lines.append(f"    {color('diagnostics:', 'bold')}")
        for diagnostic in diagnostics:
            lines.append(f"      - {diagnostic}")


def format_nested_value(value: Any, indent: int, label: str | None = None) -> list[str]:
    prefix = " " * indent
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        lines = text.splitlines() or [""]
        if label:
            return [f"{prefix}{color(label + ':', 'cyan')}"] + [f"{prefix}  {line}" for line in lines]
        return [f"{prefix}{line}" for line in lines]
    if label:
        return [f"{prefix}{color(label + ':', 'cyan')} {value}"]
    return [f"{prefix}{value}"]


def format_section(title: str) -> str:
    icon = SECTION_ICONS.get(title, "•")
    return color(f"{icon} {title}", "bold", "magenta")


def format_item(item: dict[str, Any], verbose: bool = False) -> str:
    effective = str(item.get("effective", "maybe"))
    bits = [
        color(str(item.get("scope", "unknown")), "cyan"),
        str(item.get("provider", "unknown")),
        f"effective={format_effective(effective)}",
    ]
    if item.get("managed_by"):
        bits.append(f"managed_by={item['managed_by']}")
    text = f"  {item_icon(item)} {color(str(item.get('name')), 'bold')} {color('[', 'dim')}{', '.join(bits)}{color(']', 'dim')}"
    metadata = item.get("metadata", {})
    if item.get("kind") == "plugin" and metadata:
        version = metadata.get("version")
        enabled = metadata.get("enabled")
        enabled_text = color(str(enabled), "green" if enabled else "yellow")
        text += f" version={version} enabled={enabled_text}"
    if item.get("kind") == "mcp" and metadata:
        mcp_type = metadata.get("type")
        command = metadata.get("command")
        if command:
            text += f" type={mcp_type} command={command}"
    if item.get("kind") == "hook" and metadata and metadata.get("summary"):
        text += f" summary={metadata['summary']}"
    if item.get("kind") == "skill" and metadata and metadata.get("summary"):
        text += f" summary={metadata['summary']}"
    if item.get("kind") == "permission" and metadata:
        text += f" allow={color(str(metadata.get('allow_count', 0)), 'green')} deny={color(str(metadata.get('deny_count', 0)), 'red')}"
        if verbose and metadata.get("allow"):
            text += f" allowed={metadata['allow']}"
    if verbose and item.get("source_file"):
        text += f" {color('source=', 'dim')}{item['source_file']}"
    return text


def item_icon(item: dict[str, Any]) -> str:
    if item.get("effective") in {"no", "failed"}:
        return "❌"
    if item.get("effective") == "maybe":
        return "⚠️"
    return "✅"


def format_effective(value: str) -> str:
    if value in {"yes", "ok"}:
        return color(value, "green")
    if value in {"no", "failed"}:
        return color(value, "red")
    return color(value, "yellow")


def severity_icon(severity: str) -> str:
    if severity == "ERROR":
        return "❌"
    if severity == "WARNING":
        return "⚠️"
    return "ℹ️"


def format_severity(severity: str) -> str:
    if severity == "ERROR":
        return color(severity, "red", "bold")
    if severity == "WARNING":
        return color(severity, "yellow", "bold")
    return color(severity, "blue", "bold")


def color(value: str, *names: str) -> str:
    if not use_color():
        return value
    prefix = "".join(COLORS[name] for name in names if name in COLORS)
    return f"{prefix}{value}{COLORS['reset']}" if prefix else value


def use_color() -> bool:
    return "NO_COLOR" not in os.environ


def render_markdown(status: dict[str, Any], category: str | None = None, name: str | None = None) -> str:
    lines: list[str] = []
    lines.append("# Claude Code Doctor")
    lines.append("")
    lines.append(f"- Project: `{status['project_root']}`")
    lines.append("")
    if category in {None, "provider"}:
        lines.append("## Provider / Model")
        lines.append("")
        provider_settings = status.get("provider", {}).get("settings", [])
        if not provider_settings:
            lines.append("- _no provider settings detected_")
        for setting in provider_settings:
            for key in ("model", "statusLine", "env"):
                if key in setting:
                    lines.append(f"- **{key}**: `{escape_md(str(setting[key]))}`")
        lines.append("")
    for title, key in SECTION_PAIRS:
        if category not in {None, key}:
            continue
        lines.append(f"## {title}")
        lines.append("")
        items = matching_items(status.get(key, []), name)
        if name:
            append_markdown_details(lines, items, name)
        else:
            lines.append("| Name | Scope | Provider | Effective | Source |")
            lines.append("|---|---|---|---|---|")
            if not items:
                lines.append("| _none_ |  |  |  |  |")
            for item in items:
                lines.append(
                    "| {name} | {scope} | {provider} | {effective} | {source} |".format(
                        name=escape_md(str(item.get("name", ""))),
                        scope=escape_md(str(item.get("scope", ""))),
                        provider=escape_md(str(item.get("provider", ""))),
                        effective=escape_md(str(item.get("effective", ""))),
                        source=escape_md(str(item.get("source_file", ""))),
                    )
                )
        lines.append("")
    if category in {None, "diagnostics"}:
        lines.append("## Diagnostics")
        lines.append("")
        diagnostics = matching_diagnostics(status.get("diagnostics", []), name)
        if not diagnostics:
            lines.append("- OK: no warnings or errors")
        for diagnostic in diagnostics:
            lines.append(f"- **{diagnostic.get('severity', 'info').upper()}**: {diagnostic.get('message', '')}")
    return "\n".join(lines)


def append_markdown_details(lines: list[str], items: list[dict[str, Any]], name: str) -> None:
    if not items:
        lines.append(f"_No item named `{escape_md(name)}` found._")
        return
    for item in items:
        lines.append(f"### {escape_md(str(item.get('name', '')))}")
        lines.append("")
        for key in ("kind", "scope", "provider", "effective", "managed_by", "source_file"):
            value = item.get(key)
            if value is not None:
                lines.append(f"- **{key}**: `{escape_md(str(value))}`")
        metadata = item.get("metadata", {})
        if isinstance(metadata, dict) and metadata:
            lines.append("- **metadata**:")
            lines.append("```json")
            lines.append(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True))
            lines.append("```")
        lines.append("")


def filter_status(status: dict[str, Any], category: str, name: str | None = None) -> dict[str, Any]:
    filtered: dict[str, Any] = {"project_root": status.get("project_root")}
    if category == "provider":
        filtered["provider"] = status.get("provider", {})
    elif category == "diagnostics":
        filtered["diagnostics"] = matching_diagnostics(status.get("diagnostics", []), name)
    else:
        filtered[category] = matching_items(status.get(category, []), name)
    return filtered


def matching_items(items: Any, name: str | None) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    typed_items = [item for item in items if isinstance(item, dict)]
    if not name:
        return typed_items
    needle = name.casefold()
    exact = [item for item in typed_items if str(item.get("name", "")).casefold() == needle]
    if exact:
        return exact
    return [item for item in typed_items if needle in str(item.get("name", "")).casefold()]


def matching_diagnostics(diagnostics: Any, name: str | None) -> list[dict[str, Any]]:
    if not isinstance(diagnostics, list):
        return []
    typed_diagnostics = [item for item in diagnostics if isinstance(item, dict)]
    if not name:
        return typed_diagnostics
    needle = name.casefold()
    return [
        item
        for item in typed_diagnostics
        if needle in str(item.get("message", "")).casefold()
        or needle in str(item.get("source_file", "")).casefold()
        or needle == str(item.get("severity", "")).casefold()
    ]


def escape_md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
