<div align="center">
  <a href="https://github.com/Cookie-HOO/ccdoctor">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/assets/logo-dark.svg">
      <source media="(prefers-color-scheme: light)" srcset="docs/assets/logo-light.svg">
      <img src="docs/assets/logo-dark.svg" width="100px" alt="ccdoctor" />
    </picture>
  </a>
  <h1 style="font-size: 28px; margin: 10px 0;">ccdoctor</h1>
  <p>Inspect Claude Code visibility from your terminal, scripts, and agents.</p>
</div>

<p align="center">
  <a href="https://github.com/Cookie-HOO/ccdoctor" target="_blank">
    <img alt="GitHub Repository" src="https://img.shields.io/badge/GitHub-Cookie--HOO%2Fccdoctor-181717?logo=github" />
  </a>
  <a href="https://docs.astral.sh/uv/guides/tools/" target="_blank">
    <img alt="uvx ready" src="https://img.shields.io/badge/uvx-ready-654ff0" />
  </a>
  <img alt="Python 3.12+" src="https://img.shields.io/badge/python-3.12%2B-3776ab?logo=python&amp;logoColor=white" />
  <img alt="Output modes" src="https://img.shields.io/badge/output-JSON%20%7C%20Markdown%20%7C%20TTY-0f766e" />
  <img alt="Read-only" src="https://img.shields.io/badge/safety-read--only-16a34a" />
</p>

<p align="center">
  <a href="README.zh-CN.md">简体中文</a>
  ·
  <a href="#all-demos">View Demo</a>
  ·
  <a href="https://github.com/Cookie-HOO/ccdoctor/issues/new?labels=bug">Report Bug</a>
  ·
  <a href="https://github.com/Cookie-HOO/ccdoctor/issues/new?labels=enhancement">Request Feature</a>
  ·
  <a href="#agent-and-llm-usage">Agent Usage</a>
  ·
  <a href="#command-reference">Command Reference</a>
</p>

<br>

`ccdoctor` is a local diagnostics CLI for Claude Code projects. It reports what Claude Code can see from a project root: MCPs, skills, hooks, plugins, provider/model settings, agents, permissions, statusline configuration, diagnostics, and declared governance manifests.

It is intentionally a shell CLI instead of a global MCP. You can run it from any terminal, CI job, script, or agent without adding another always-visible MCP server to Claude Code.

> [!TIP]
> For agents and LLM pipelines, prefer narrow JSON queries: `NO_COLOR=1 ccd --json <category> [name] -p <project>`.

<details>
<summary>Table of contents (Click to show)</summary>

- [Why use ccdoctor?](#why-use-ccdoctor)
- [Quickstart](#quickstart)
- [All Demos](#all-demos)
  - [Project overview](#project-overview)
  - [Category view](#category-view)
  - [Item detail view](#item-detail-view)
  - [JSON automation](#json-automation)
  - [Markdown output](#markdown-output)
  - [Doctor mode](#doctor-mode)
- [Command reference](#command-reference)
  - [Options](#options)
  - [Categories](#categories)
- [Output field reference](#output-field-reference)
  - [`scope` values](#scope-values)
  - [`provider` values](#provider-values)
  - [`effective` values](#effective-values)
  - [Diagnostic severities](#diagnostic-severities)
- [Agent and LLM usage](#agent-and-llm-usage)
- [Safety](#safety)
- [Resources](#resources)

</details>

# Why use ccdoctor?

Claude Code configuration can come from several places at once: project files, user settings, plugins, symlinks, manifests, nested project roots, and runtime defaults. `ccdoctor` gives you one read-only report that separates what is configured, what is declared, and what is expected to be effective.

- **Visibility debugging** — See the MCPs, skills, hooks, plugins, agents, provider settings, and permissions Claude Code can discover for a project.
- **Agent-friendly inspection** — Use filtered JSON output so agents can reason over config without reading unrelated files.
- **Governance checks** — Compare project/runtime state against declared manifests and flag stale or nested config.
- **Safe diagnostics** — Runs read-only by default and redacts values whose keys look like tokens, keys, secrets, cookies, passwords, or auth fields.
- **Multiple output modes** — Human terminal output, JSON for automation, Markdown for PRs/issues, and `--doctor` exit codes for scripts.

# Quickstart

Run once without installing:

```bash
uvx ccdoctor
uvx --from ccdoctor ccd mcp
```

Install once, then run `ccd` anywhere:

```bash
uv tool install ccdoctor
ccd
ccd mcp
```

Install from GitHub instead of PyPI:

```bash
uv tool install git+https://github.com/Cookie-HOO/ccdoctor
ccd
```

Inspect another project:

```bash
ccd -p ~/Projects/my_ai
```

Inspect one category or one item:

```bash
ccd mcp
ccd mcp playwright
ccd hook PreToolUse
ccd skill profile-project-manager
```

Get machine-readable output:

```bash
NO_COLOR=1 ccd --json mcp playwright -p ~/Projects/my_ai
```

# All Demos

<p align="center">
  <img alt="ccdoctor terminal demo" src="docs/assets/ccdoctor-demo.svg" width="800px" />
</p>

## Project overview

```bash
ccd -p ~/Projects/my_ai
```

```text
✨ Claude Code Doctor
📁 Project: /Users/example/Projects/my_ai

🧠 Provider / Model
  • 🧠 model: claude-opus-4-8

🔌 Plugins
  ✅ claude-mem@thedotmack [user, installed-plugin, effective=yes]

🧰 MCPs
  ✅ playwright [project, configured, effective=yes] type=stdio command=/bin/zsh
  ⚠️ fetch [declared, declared, effective=maybe, managed_by=my_ai manifest]
```

## Category view

```bash
ccd mcp -p ~/Projects/my_ai
```

```text
✨ Claude Code Doctor
📁 Project: /Users/example/Projects/my_ai

🧰 MCPs
  ✅ playwright [project, configured, effective=yes] type=stdio command=/bin/zsh source=/Users/example/Projects/my_ai/.mcp.json
  ✅ mcp-search [user, plugin-provided, effective=yes, managed_by=claude-mem@thedotmack] type=stdio command=node
  ⚠️ fetch [declared, declared, effective=maybe, managed_by=my_ai manifest]
```

## Item detail view

```bash
ccd mcp playwright -p ~/Projects/my_ai
```

```text
🧰 MCPs
  ✅ playwright [project, configured, effective=yes] type=stdio command=/bin/zsh source=/Users/example/Projects/my_ai/.mcp.json
    kind: mcp
    name: playwright
    scope: project
    provider: configured
    effective: yes
    source_file: /Users/example/Projects/my_ai/.mcp.json
    metadata:
      type: stdio
      command: /bin/zsh
      args:
        [
          "-lc",
          "node \"$MY_AI_ROOT/mcps/playwright-mcp/node_modules/@playwright/mcp/cli.js\""
        ]
      tools:
        [
          {
            "name": "browser_click",
            "description": "Perform click on a web page"
          }
        ]
```

Hook details work the same way:

```bash
ccd hook PreToolUse -p ~/Projects/my_ai
```

```text
🪝 Hooks
  ✅ PreToolUse [user, configured, effective=yes] summary=[{"hooks": [{"command": "...", "type": "command"}], "matcher": "*"}]
    kind: hook
    name: PreToolUse
    scope: user
    provider: configured
    effective: yes
    source_file: /Users/example/.claude/settings.json
    metadata:
      config:
        [
          {
            "hooks": [{"command": "...", "type": "command"}],
            "matcher": "*"
          }
        ]
```

## JSON automation

```bash
ccd --json mcp playwright -p ~/Projects/my_ai
```

```json
{
  "mcps": [
    {
      "effective": "yes",
      "kind": "mcp",
      "metadata": {
        "args": ["-lc", "node \"$MY_AI_ROOT/mcps/playwright-mcp/node_modules/@playwright/mcp/cli.js\""],
        "command": "/bin/zsh",
        "type": "stdio"
      },
      "name": "playwright",
      "provider": "configured",
      "scope": "project",
      "source_file": "/Users/example/Projects/my_ai/.mcp.json"
    }
  ],
  "project_root": "/Users/example/Projects/my_ai"
}
```

## Markdown output

```bash
ccd --markdown hook PreToolUse -p ~/Projects/my_ai
```

This produces Markdown headings and JSON metadata blocks suitable for pasting into a GitHub issue or PR comment.

## Doctor mode

```bash
ccd --doctor -p ~/Projects/my_ai
```

| Code | Meaning |
|---:|---|
| `0` | No warnings or errors. |
| `1` | Warning diagnostics were found. |
| `2` | Error diagnostics were found. |

# Command reference

```text
ccd [options] [category] [name]
ccdoctor [options] [category] [name]
```

## Options

| Option | Meaning |
|---|---|
| `-p, --project PATH` | Inspect another project directory. Defaults to the current directory. |
| `--json` | Print stable redacted JSON for automation. |
| `--markdown` | Print Markdown tables/details for issues and PRs. |
| `--doctor` | Return non-zero when warnings/errors are found. |
| `--verbose, -v` | Include source paths, allowlists, and diagnostic hints. |
| `--include-runtime` | Run optional read-only runtime probes, currently localhost proxy `/health`. |

## Categories

| Category | Aliases | What it shows |
|---|---|---|
| Provider/model | `provider`, `model` | Model, statusline, Claude/Anthropic environment settings, optional runtime probe. |
| Plugins | `plugin`, `plugins` | Installed/enabled Claude Code plugins and plugin metadata. |
| MCPs | `mcp`, `mcps` | Global, project, nested-project, plugin-provided, and manifest-declared MCP servers. |
| Skills | `skill`, `skills` | Global skills, project skills, plugin-provided skills, and runtime/manifest-declared skills. |
| Agents | `agent`, `agents` | Project agents, profile-provided agents, and plugin-provided agents. |
| Hooks | `hook`, `hooks` | User/project hooks and plugin-provided hook events. |
| Permissions | `permission`, `permissions` | Claude Code allow/deny permission settings. |
| Diagnostics | `diagnostic`, `diagnostics`, `diag` | Warnings and errors discovered while collecting status. |

Passing a `name` after a category narrows output to matching entries and prints detail metadata. For configured stdio MCPs, the MCP detail view also starts the selected server briefly and lists its available tools and descriptions when the server responds to `tools/list`:

```bash
ccd mcp playwright
ccd hook PreToolUse
ccd skill profile-project-manager
ccd plugin claude-mem
```

# Output field reference

Every collected record is a `StatusItem` with common fields:

| Field | Meaning |
|---|---|
| `kind` | Record type, such as `mcp`, `skill`, `hook`, `plugin`, `agent`, or `permission`. |
| `name` | Human-readable record name. |
| `scope` | Where the record comes from. |
| `provider` | How the record is provided or managed. |
| `effective` | Whether Claude Code should actually see or use the record. |
| `managed_by` | Optional owner/manager, such as a plugin name or `my_ai manifest`. |
| `source_file` | File or directory where the record was discovered. |
| `metadata` | Type-specific details, redacted where keys look secret-like. |
| `diagnostics` | Item-local diagnostic notes when present. |

## `scope` values

| Value | Meaning |
|---|---|
| `project` | Directly configured in the inspected project. Usually effective when Claude is launched there. |
| `global` | Comes from global Claude Code configuration, such as `~/.claude.json` MCP servers or `~/.claude/skills`. |
| `user` | Comes from the current user's Claude Code configuration or plugin installation. |
| `nested-project` | Found under the project tree but not at the inspected root. Usually not effective for this root. |
| `runtime` | Declared as available from the Claude Code runtime or generated runtime manifest. |
| `declared` | Present in a governance manifest, but not necessarily configured for runtime use. |
| `custom` | A custom local source, currently used for some agent/profile records. |

## `provider` values

| Value | Meaning |
|---|---|
| `configured` | Found in a concrete Claude Code config file, such as `.mcp.json` or `.claude/settings.json`. |
| `custom` | Comes from this repository's custom skill/tool/profile area. |
| `installed` | Comes from this repository's installed managed assets. |
| `installed-plugin` | Comes from Claude Code's installed plugin registry. |
| `plugin-provided` | Provided by a Claude Code plugin. |
| `runtime-built-in` | Declared by the Claude Code runtime or runtime skill list. |
| `profile-provided` | Comes from a project profile definition. |
| `declared` | Listed in a manifest for tracking/governance. |

## `effective` values

| Value | Meaning |
|---|---|
| `yes` | Expected to be visible/effective for the inspected project. |
| `no` | Found but not expected to be effective for the inspected project. |
| `maybe` | Declared or inferred, but runtime effectiveness cannot be proven from static files alone. |
| `ok` | Runtime probe succeeded. |
| `failed` | Runtime probe failed. |

## Diagnostic severities

| Severity | Meaning |
|---|---|
| `info` | Informational note. |
| `warning` | Something may be stale, ineffective, missing, or surprising. `--doctor` exits `1`. |
| `error` | Something is malformed or broken enough to require action. `--doctor` exits `2`. |

# Agent and LLM usage

For agents and LLM pipelines, prefer narrow JSON queries. They are smaller, stable, and easier to parse than terminal output.

```bash
NO_COLOR=1 ccd --json <category> [name] -p <project>
```

Examples:

```bash
NO_COLOR=1 ccd --json mcp playwright -p /repo
NO_COLOR=1 ccd --json hook PreToolUse -p /repo
NO_COLOR=1 ccd --json skill profile-project-manager -p /repo
NO_COLOR=1 ccd --json diagnostics -p /repo
```

Recommended agent flow:

1. Start with `ccd --json diagnostics -p <project>`.
2. If diagnostics mention MCPs, run `ccd --json mcp -p <project>`.
3. Query a specific item with `ccd --json mcp <name> -p <project>` before recommending config changes.
4. Quote `source_file`, `scope`, `provider`, and `effective` in your answer so the user can verify the finding.

Prompt snippet:

```text
Run `NO_COLOR=1 ccd --json diagnostics -p <project>`. If warnings or errors exist, inspect the relevant category with `ccd --json <category> [name] -p <project>`. Do not modify files. Summarize findings with source_file, scope, provider, effective, and a recommended next action.
```

Why JSON instead of text for agents?

- `--json` has no ANSI color codes.
- It includes redacted metadata needed for reasoning.
- It can be filtered by category and name to reduce token use.
- It avoids over-reading unrelated project configuration.

# Safety

`ccdoctor` is read-only by default. It does not modify Claude Code settings, plugin config, MCP config, or project files. It does not read `.env` files. Values whose keys look like tokens, keys, secrets, cookies, passwords, or auth fields are redacted before output.

Optional runtime probing only runs when `--include-runtime` is passed. Runtime probing is restricted to localhost-style endpoints such as `127.0.0.1` or `localhost`.

Manifest-only entries are treated as declared governance state, not proof of runtime visibility.

---

# Resources

- [uv tools guide](https://docs.astral.sh/uv/guides/tools/) — run Python command-line tools with `uvx`.
- [Claude Code documentation](https://docs.anthropic.com/en/docs/claude-code) — Claude Code concepts and configuration.
- [GitHub repository](https://github.com/Cookie-HOO/ccdoctor) — source, issues, and releases.
