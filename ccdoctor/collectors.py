from __future__ import annotations

import json
import os
import re
import select
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .classifiers import classify_skill_target, redact_any, redact_mapping
from .diagnostics import check_absolute_path
from .models import Diagnostic, StatusItem

USER_CLAUDE_DIR = Path.home() / ".claude"
PLUGIN_CACHE_DIR = USER_CLAUDE_DIR / "plugins" / "cache"


def get_control_root() -> Path:
    return Path(__file__).resolve().parents[4]


def collect_status(project_root: Path, include_runtime: bool = False, verbose: bool = False, mcp_tool_name: str | None = None) -> dict[str, Any]:
    project_root = project_root.resolve(strict=False)
    control_root = get_control_root()
    diagnostics: list[Diagnostic] = []

    user_state_path = Path.home() / ".claude.json"
    user_settings_path = USER_CLAUDE_DIR / "settings.json"
    user_local_settings_path = USER_CLAUDE_DIR / "settings.local.json"
    project_settings_path = project_root / ".claude" / "settings.json"
    project_local_settings_path = project_root / ".claude" / "settings.local.json"

    user_state = read_json(user_state_path, diagnostics, optional=True)
    user_settings = read_json(user_settings_path, diagnostics)
    user_local_settings = read_json(user_local_settings_path, diagnostics, optional=True)
    project_settings = read_json(project_settings_path, diagnostics, optional=True)
    project_local_settings = read_json(project_local_settings_path, diagnostics, optional=True)

    enabled_plugins = user_settings.get("enabledPlugins", {}) if isinstance(user_settings, dict) else {}
    provider = collect_provider(user_settings, user_local_settings, project_settings, project_local_settings)

    plugins = collect_plugins(enabled_plugins, diagnostics)
    mcps = collect_mcps(project_root, control_root, plugins, diagnostics, user_state=user_state, tool_name=mcp_tool_name)
    skills = collect_skills(project_root, control_root, plugins, diagnostics)
    agents = collect_agents(project_root, control_root, plugins)
    hooks = collect_hooks(project_root, user_settings, user_local_settings, project_settings, project_local_settings, plugins)
    permissions = collect_permissions(project_settings, project_local_settings, user_settings, user_local_settings)

    if include_runtime:
        probe_runtime(provider, diagnostics)

    status = {
        "project_root": str(project_root),
        "control_root": str(control_root),
        "sources": collect_sources(project_root, control_root, verbose, user_state_path),
        "provider": provider,
        "plugins": sorted_items(plugins),
        "mcps": sorted_items(mcps),
        "skills": sorted_items(skills),
        "agents": sorted_items(agents),
        "hooks": sorted_items(hooks),
        "permissions": sorted_items(permissions),
        "diagnostics": [d.to_dict() for d in diagnostics],
    }
    return status


def read_json(path: Path, diagnostics: list[Diagnostic], optional: bool = False) -> dict[str, Any]:
    if not path.exists():
        if not optional:
            diagnostics.append(Diagnostic("warning", f"JSON file not found: {path}", str(path)))
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        diagnostics.append(Diagnostic("error", f"Malformed JSON: {exc}", str(path)))
    except OSError as exc:
        diagnostics.append(Diagnostic("error", f"Cannot read JSON: {exc}", str(path)))
    return {}


def read_text(path: Path, diagnostics: list[Diagnostic], optional: bool = False) -> str:
    if not path.exists():
        if not optional:
            diagnostics.append(Diagnostic("warning", f"Text file not found: {path}", str(path)))
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        diagnostics.append(Diagnostic("warning", f"Cannot read text file: {exc}", str(path)))
        return ""


def collect_provider(*settings_objects: dict[str, Any]) -> dict[str, Any]:
    provider: dict[str, Any] = {"settings": []}
    for settings in settings_objects:
        if not settings:
            continue
        redacted = redact_mapping(settings)
        entry: dict[str, Any] = {}
        for key in ("model", "statusLine", "enabledPlugins"):
            if key in redacted:
                entry[key] = redacted[key]
        if "env" in redacted:
            env = redacted["env"]
            if isinstance(env, dict):
                entry["env"] = {
                    key: env[key]
                    for key in sorted(env)
                    if key.startswith("ANTHROPIC") or key.startswith("CLAUDE")
                }
        if entry:
            provider["settings"].append(entry)
    return provider


def summarize_value(value: Any, max_items: int = 3, max_length: int = 220) -> str:
    value = redact_any(value)
    if isinstance(value, dict):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    elif isinstance(value, list):
        shown = value[:max_items]
        text = json.dumps(shown, ensure_ascii=False, sort_keys=True)
        if len(value) > max_items:
            text += f" (+{len(value) - max_items} more)"
    else:
        text = str(value)
    return truncate(text, max_length)


def truncate(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 1].rstrip() + "…"


def collect_plugins(enabled_plugins: dict[str, Any], diagnostics: list[Diagnostic]) -> list[StatusItem]:
    installed_path = USER_CLAUDE_DIR / "plugins" / "installed_plugins.json"
    installed = read_json(installed_path, diagnostics, optional=True)
    installed_plugins = installed.get("plugins", {}) if isinstance(installed, dict) else {}
    installed_paths: set[str] = set()
    items: list[StatusItem] = []

    for key, installs in installed_plugins.items():
        if not isinstance(installs, list):
            continue
        for install in installs:
            if not isinstance(install, dict):
                continue
            install_path = Path(str(install.get("installPath", ""))).expanduser()
            installed_paths.add(str(install_path))
            enabled = bool(enabled_plugins.get(key, False)) if isinstance(enabled_plugins, dict) else False
            metadata = {
                "version": install.get("version"),
                "enabled": enabled,
                "install_path": str(install_path),
                "components": plugin_components(install_path),
            }
            plugin_json = install_path / ".claude-plugin" / "plugin.json"
            plugin_meta = read_plugin_metadata(plugin_json)
            if plugin_meta:
                metadata["plugin"] = redact_mapping(plugin_meta)
            if not install_path.exists():
                diagnostics.append(Diagnostic("error", f"Installed plugin path missing: {install_path}", str(installed_path)))
            items.append(StatusItem(
                kind="plugin",
                name=key,
                scope=str(install.get("scope", "user")),
                provider="installed-plugin",
                source_file=str(installed_path),
                effective="yes" if enabled else "no",
                managed_by="Claude Code plugin system",
                metadata=metadata,
            ))

    if isinstance(enabled_plugins, dict):
        for key, enabled in enabled_plugins.items():
            if enabled and key not in installed_plugins:
                diagnostics.append(Diagnostic(
                    "warning",
                    f"Plugin is enabled but not present in installed registry: {key}",
                    str(USER_CLAUDE_DIR / "settings.json"),
                ))

    if PLUGIN_CACHE_DIR.exists():
        for plugin_json in PLUGIN_CACHE_DIR.glob("*/*/*/.claude-plugin/plugin.json"):
            cache_root = plugin_json.parents[1]
            if str(cache_root) not in installed_paths:
                diagnostics.append(Diagnostic(
                    "warning",
                    f"Plugin cache exists but is not selected by installed registry: {cache_root}",
                    str(plugin_json),
                ))
    return items


def read_plugin_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def plugin_components(install_path: Path) -> dict[str, Any]:
    components: dict[str, Any] = {}
    for name in ("skills", "hooks", "commands", "modes", "agents"):
        directory = install_path / name
        if directory.exists() and directory.is_dir():
            components[name] = sorted(child.name for child in directory.iterdir() if not child.name.startswith("."))
        else:
            components[name] = []
    mcp_path = install_path / ".mcp.json"
    if mcp_path.exists():
        try:
            config = json.loads(mcp_path.read_text(encoding="utf-8"))
            components["mcp_servers"] = sorted((config.get("mcpServers") or {}).keys())
        except (OSError, json.JSONDecodeError):
            components["mcp_servers"] = []
    else:
        components["mcp_servers"] = []
    return components


def collect_mcps(
    project_root: Path,
    control_root: Path,
    plugins: list[StatusItem],
    diagnostics: list[Diagnostic],
    user_state: dict[str, Any],
    tool_name: str | None = None,
) -> list[StatusItem]:
    items: list[StatusItem] = []
    user_state_path = Path.home() / ".claude.json"
    collect_mcp_servers(user_state.get("mcpServers", {}) if isinstance(user_state, dict) else {}, "global", "configured", "yes", str(user_state_path), items, diagnostics, tool_name=tool_name)

    project_mcp = project_root / ".mcp.json"
    collect_mcp_config(project_mcp, "project", "configured", "yes", items, diagnostics, tool_name=tool_name)

    for plugin in plugins:
        install_path = plugin.metadata.get("install_path")
        if not install_path:
            continue
        mcp_path = Path(str(install_path)) / ".mcp.json"
        collect_mcp_config(mcp_path, "user", "plugin-provided", plugin.effective, items, diagnostics, managed_by=plugin.name, tool_name=tool_name)

    for nested_mcp in find_nested_mcp_configs(project_root):
        collect_mcp_config(nested_mcp, "nested-project", "configured", "no", items, diagnostics, tool_name=tool_name)
        diagnostics.append(Diagnostic(
            "warning",
            f"Nested .mcp.json is not effective for project root unless Claude is launched there: {nested_mcp}",
            str(nested_mcp),
        ))

    manifest_path = control_root / "mcps" / "MCP_MANIFEST.md"
    for name in parse_manifest_names(manifest_path, diagnostics):
        items.append(StatusItem(
            kind="mcp",
            name=name,
            scope="declared",
            provider="declared",
            source_file=str(manifest_path),
            effective="maybe",
            managed_by="my_ai manifest",
        ))
    return items


def collect_mcp_config(
    path: Path,
    scope: str,
    provider: str,
    effective: str,
    items: list[StatusItem],
    diagnostics: list[Diagnostic],
    managed_by: str | None = None,
    tool_name: str | None = None,
) -> None:
    if not path.exists():
        return
    config = read_json(path, diagnostics, optional=True)
    servers = config.get("mcpServers", {}) if isinstance(config, dict) else {}
    collect_mcp_servers(servers, scope, provider, effective, str(path), items, diagnostics, managed_by=managed_by, tool_name=tool_name)


def collect_mcp_servers(
    servers: Any,
    scope: str,
    provider: str,
    effective: str,
    source_file: str,
    items: list[StatusItem],
    diagnostics: list[Diagnostic],
    managed_by: str | None = None,
    tool_name: str | None = None,
) -> None:
    if not isinstance(servers, dict):
        return
    for name, server in servers.items():
        server = server if isinstance(server, dict) else {}
        metadata = redact_mapping({
            "type": server.get("type"),
            "command": server.get("command"),
            "args": server.get("args", []),
            "env": server.get("env", {}),
            "config": server,
        })
        if tool_name and mcp_name_matches(str(name), tool_name):
            tools = collect_mcp_tools(server, diagnostics, source_file, str(name))
            if tools:
                metadata["tools"] = tools
        severity = "warning" if scope == "nested-project" else "error"
        for label, value in (("MCP command", server.get("command")),):
            diag = check_absolute_path(value, source_file, label, severity=severity)
            if diag:
                diagnostics.append(diag)
        for arg in server.get("args", []) if isinstance(server.get("args", []), list) else []:
            diag = check_absolute_path(arg, source_file, "MCP argument path", severity=severity)
            if diag:
                diagnostics.append(diag)
        items.append(StatusItem(
            kind="mcp",
            name=str(name),
            scope=scope,
            provider=provider,
            source_file=source_file,
            effective=effective,
            managed_by=managed_by,
            metadata=metadata,
        ))


def mcp_name_matches(name: str, requested: str) -> bool:
    name_key = name.casefold()
    requested_key = requested.casefold()
    return name_key == requested_key or requested_key in name_key


def collect_mcp_tools(server: dict[str, Any], diagnostics: list[Diagnostic], source_file: str, name: str) -> list[dict[str, Any]]:
    if server.get("type") not in {None, "stdio"}:
        return []
    command = server.get("command")
    if not isinstance(command, str) or not command:
        return []
    args = server.get("args", [])
    if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
        return []
    env = os.environ.copy()
    server_env = server.get("env", {})
    if isinstance(server_env, dict):
        for key, value in server_env.items():
            if isinstance(key, str) and isinstance(value, str):
                env[key] = os.path.expandvars(value)
    try:
        proc = subprocess.Popen(
            [os.path.expandvars(command), *[os.path.expandvars(arg) for arg in args]],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
        )
    except OSError as exc:
        diagnostics.append(Diagnostic("warning", f"Cannot start MCP server to list tools for {name}: {exc}", source_file))
        return []

    try:
        responses = exchange_mcp_messages(proc, [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "ccdoctor", "version": "0.1.0"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ])
    finally:
        terminate_process(proc)

    tools_result = next((response.get("result") for response in responses if response.get("id") == 2), None)
    tools = tools_result.get("tools", []) if isinstance(tools_result, dict) else []
    if not isinstance(tools, list):
        return []
    collected: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        tool_name = tool.get("name")
        if not isinstance(tool_name, str) or not tool_name:
            continue
        entry = {"name": tool_name}
        description = tool.get("description")
        if isinstance(description, str) and description:
            entry["description"] = description
        collected.append(redact_mapping(entry))
    return collected


def exchange_mcp_messages(proc: subprocess.Popen[bytes], messages: list[dict[str, Any]], timeout: float = 3.0) -> list[dict[str, Any]]:
    responses: list[dict[str, Any]] = []
    for message in messages:
        if proc.stdin is None:
            break
        proc.stdin.write(json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n")
        proc.stdin.flush()
        if "id" in message:
            responses.extend(read_mcp_responses(proc, target_id=message["id"], timeout=timeout))
    return responses


def read_mcp_responses(proc: subprocess.Popen[bytes], target_id: Any, timeout: float) -> list[dict[str, Any]]:
    responses: list[dict[str, Any]] = []
    if proc.stdout is None:
        return responses
    fd = proc.stdout.fileno()
    while True:
        ready, _, _ = select.select([fd], [], [], timeout)
        if not ready:
            break
        line = proc.stdout.readline()
        if not line:
            break
        try:
            response = json.loads(line.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            continue
        if not isinstance(response, dict):
            continue
        responses.append(response)
        if response.get("id") == target_id:
            break
    return responses


def terminate_process(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=1.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=1.0)


def find_nested_mcp_configs(project_root: Path) -> list[Path]:
    nested: list[Path] = []
    skip_parts = {".git", ".venv", "node_modules", "__pycache__"}
    try:
        for path in project_root.rglob(".mcp.json"):
            if path == project_root / ".mcp.json":
                continue
            if any(part in skip_parts for part in path.parts):
                continue
            nested.append(path)
    except OSError:
        return []
    return sorted(nested)


def parse_manifest_names(path: Path, diagnostics: list[Diagnostic]) -> list[str]:
    text = read_text(path, diagnostics, optional=True)
    names: list[str] = []
    for match in re.finditer(r"^\|\s*`([^`]+)`\s*\|", text, flags=re.MULTILINE):
        name = match.group(1)
        if name not in names:
            names.append(name)
    return names


def collect_skills(project_root: Path, control_root: Path, plugins: list[StatusItem], diagnostics: list[Diagnostic]) -> list[StatusItem]:
    items: list[StatusItem] = []
    collect_skill_directory(USER_CLAUDE_DIR / "skills", "global", control_root, items, diagnostics)
    collect_skill_directory(project_root / ".claude" / "skills", "project", control_root, items, diagnostics)

    for plugin in plugins:
        install_path = plugin.metadata.get("install_path")
        if not install_path:
            continue
        skills_dir = Path(str(install_path)) / "skills"
        if not skills_dir.exists():
            continue
        for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
            items.append(StatusItem(
                kind="skill",
                name=skill_md.parent.name,
                scope="user",
                provider="plugin-provided",
                source_file=str(skill_md),
                effective=plugin.effective,
                managed_by=plugin.name,
                metadata={"summary": read_skill_summary(skill_md, diagnostics)},
            ))

    manifest_path = control_root / "skills" / "SKILL_MANIFEST.md"
    for name in parse_runtime_skills(manifest_path, diagnostics):
        items.append(StatusItem(
            kind="skill",
            name=name,
            scope="runtime",
            provider="runtime-built-in",
            source_file=str(manifest_path),
            effective="maybe",
            managed_by="Claude Code runtime / manifest",
        ))
    return items


def collect_skill_directory(directory: Path, scope: str, control_root: Path, items: list[StatusItem], diagnostics: list[Diagnostic]) -> None:
    if not directory.exists():
        return
    for child in sorted(directory.iterdir(), key=lambda p: p.name):
        if child.name.startswith("."):
            continue
        target = None
        target_exists = child.exists()
        if child.is_symlink():
            try:
                target = child.resolve(strict=False)
                target_exists = target.exists()
            except OSError:
                target_exists = False
        provider, managed_by = classify_skill_target(target or child, control_root)
        metadata = {"path": str(child), "target": str(target) if target else None, "target_exists": target_exists}
        skill_file = (target or child) / "SKILL.md" if (target or child).is_dir() else (target or child)
        metadata["summary"] = read_skill_summary(skill_file, diagnostics)
        if not target_exists:
            diagnostics.append(Diagnostic("error", f"Broken {scope} skill link/path: {child}", str(child)))
        items.append(StatusItem(
            kind="skill",
            name=child.name,
            scope=scope,
            provider=provider,
            source_file=str(child),
            effective="yes" if target_exists else "no",
            managed_by=managed_by,
            metadata={k: v for k, v in metadata.items() if v is not None},
        ))


def read_skill_summary(path: Path, diagnostics: list[Diagnostic], max_lines: int = 12) -> str:
    text = read_text(path, diagnostics, optional=True)
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("---") or line.startswith("#"):
            continue
        lines.append(line)
        if len(lines) >= max_lines:
            break
    return truncate(" ".join(lines), 500)


def parse_runtime_skills(path: Path, diagnostics: list[Diagnostic]) -> list[str]:
    text = read_text(path, diagnostics, optional=True)
    start = text.find("## Runtime Skills")
    if start < 0:
        return []
    rest = text[start:]
    next_section = rest.find("\n## ", 1)
    section = rest if next_section < 0 else rest[:next_section]
    names: list[str] = []
    for match in re.finditer(r"^\|\s*`([^`]+)`\s*\|", section, flags=re.MULTILINE):
        names.append(match.group(1))
    return names


def collect_agents(project_root: Path, control_root: Path, plugins: list[StatusItem]) -> list[StatusItem]:
    items: list[StatusItem] = []
    for scope, agents_dir, provider, managed_by, effective in (
        ("project", project_root / ".claude" / "agents", "configured", "project", "yes"),
        ("custom", control_root / "profiles", "profile-provided", "my_ai profile", "maybe"),
    ):
        if not agents_dir.exists():
            continue
        pattern = "*.md" if scope == "project" else "*/agents/*.md"
        for agent_file in sorted(agents_dir.glob(pattern)):
            items.append(StatusItem(
                kind="agent",
                name=agent_file.stem,
                scope="project" if scope == "project" else "declared",
                provider=provider,
                source_file=str(agent_file),
                effective=effective,
                managed_by=managed_by,
            ))

    for plugin in plugins:
        components = plugin.metadata.get("components", {})
        agent_names = components.get("agents", []) if isinstance(components, dict) else []
        for name in agent_names:
            items.append(StatusItem(
                kind="agent",
                name=str(name),
                scope="user",
                provider="plugin-provided",
                source_file=str(plugin.metadata.get("install_path")),
                effective=plugin.effective,
                managed_by=plugin.name,
            ))
    return items


def collect_hooks(project_root: Path, *settings_and_plugins: Any) -> list[StatusItem]:
    user_settings, user_local, project_settings, project_local, plugins = settings_and_plugins
    items: list[StatusItem] = []
    for scope, source, settings in (
        ("user", str(USER_CLAUDE_DIR / "settings.json"), user_settings),
        ("user", str(USER_CLAUDE_DIR / "settings.local.json"), user_local),
        ("project", str(project_root / ".claude" / "settings.json"), project_settings),
        ("project", str(project_root / ".claude" / "settings.local.json"), project_local),
    ):
        hooks = settings.get("hooks") if isinstance(settings, dict) else None
        if isinstance(hooks, dict):
            for event_name in sorted(hooks):
                hook_config = hooks.get(event_name)
                metadata = redact_mapping({
                    "config": hook_config,
                    "summary": summarize_value(hook_config),
                })
                items.append(StatusItem("hook", str(event_name), scope, "configured", source, "yes", metadata=metadata))

    for plugin in plugins:
        hook_names = plugin_hook_events(plugin)
        for hook_name in hook_names:
            items.append(StatusItem(
                kind="hook",
                name=str(hook_name),
                scope="user",
                provider="plugin-provided",
                source_file=str(plugin.metadata.get("install_path")),
                effective=plugin.effective,
                managed_by=plugin.name,
            ))
    return items


def plugin_hook_events(plugin: StatusItem) -> list[str]:
    if plugin.name == "claude-mem@thedotmack":
        return ["Setup", "SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"]

    components = plugin.metadata.get("components", {})
    hook_names = components.get("hooks", []) if isinstance(components, dict) else []
    known_events = {
        "Notification",
        "PermissionRequest",
        "PostToolUse",
        "PostToolUseFailure",
        "PreCompact",
        "PreToolUse",
        "SessionEnd",
        "SessionStart",
        "Stop",
        "StopFailure",
        "SubagentStart",
        "SubagentStop",
        "UserPromptSubmit",
    }
    return [str(name) for name in hook_names if str(name) in known_events]


def collect_permissions(project_settings: dict[str, Any], project_local: dict[str, Any], user_settings: dict[str, Any], user_local: dict[str, Any]) -> list[StatusItem]:
    items: list[StatusItem] = []
    for scope, source, settings in (
        ("project", "project .claude/settings.json", project_settings),
        ("project", "project .claude/settings.local.json", project_local),
        ("user", "user settings.json", user_settings),
        ("user", "user settings.local.json", user_local),
    ):
        permissions = settings.get("permissions") if isinstance(settings, dict) else None
        if isinstance(permissions, dict):
            allow = permissions.get("allow", []) if isinstance(permissions.get("allow", []), list) else []
            deny = permissions.get("deny", []) if isinstance(permissions.get("deny", []), list) else []
            items.append(StatusItem(
                kind="permission",
                name=source,
                scope=scope,
                provider="configured",
                effective="yes",
                metadata={"allow_count": len(allow), "deny_count": len(deny), "allow": allow, "deny": deny},
            ))
    return items


def probe_runtime(provider: dict[str, Any], diagnostics: list[Diagnostic]) -> None:
    base_url = None
    for setting in provider.get("settings", []):
        env = setting.get("env", {}) if isinstance(setting, dict) else {}
        if isinstance(env, dict) and isinstance(env.get("ANTHROPIC_BASE_URL"), str):
            base_url = env["ANTHROPIC_BASE_URL"]
            break
    if not base_url:
        return
    parsed = urlparse(base_url)
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        return
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/health", timeout=1.0) as response:
            payload = response.read(2048).decode("utf-8", errors="replace")
        provider["runtime_probe"] = {"health_url": base_url.rstrip("/") + "/health", "ok": True, "response": payload}
    except (OSError, urllib.error.URLError) as exc:
        diagnostics.append(Diagnostic("warning", f"Local proxy health probe failed: {exc}", base_url))


def collect_sources(project_root: Path, control_root: Path, verbose: bool, user_state_path: Path) -> dict[str, Any]:
    sources = {
        "user_settings": str(USER_CLAUDE_DIR / "settings.json"),
        "plugin_registry": str(USER_CLAUDE_DIR / "plugins" / "installed_plugins.json"),
        "project_mcp": str(project_root / ".mcp.json"),
        "project_settings": str(project_root / ".claude"),
        "control_manifests": [
            str(user_state_path),
            str(control_root / "tools" / "TOOL_MANIFEST.md"),
            str(control_root / "skills" / "SKILL_MANIFEST.md"),
            str(control_root / "plugins" / "PLUGIN_MANIFEST.md"),
            str(control_root / "hooks" / "HOOK_MANIFEST.md"),
            str(control_root / "mcps" / "MCP_MANIFEST.md"),
        ],
    }
    if verbose:
        sources["plugin_cache"] = str(PLUGIN_CACHE_DIR)
    return sources


def sorted_items(items: list[StatusItem]) -> list[dict[str, Any]]:
    return [item.to_dict() for item in sorted(items, key=lambda item: item.sort_key())]
