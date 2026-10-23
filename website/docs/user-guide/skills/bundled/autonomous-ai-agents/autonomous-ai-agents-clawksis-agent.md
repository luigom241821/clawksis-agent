---
title: "Clawksis Agent — Use, configure, theme, extend, and orchestrate Clawksis"
sidebar_label: "Clawksis Agent"
description: "Use, configure, theme, extend, and orchestrate Clawksis"
---

{/* This page is auto-generated from the skill's SKILL.md by website/scripts/generate-skill-docs.py. Edit the source SKILL.md, not this page. */}

# Clawksis Agent

Use, configure, theme, extend, and orchestrate Clawksis.

## Skill metadata

| | |
|---|---|
| Source | Bundled (installed by default) |
| Path | `skills/autonomous-ai-agents/clawksis-agent` |
| Version | `3.2.0` |
| Author | Clawksis + Teknium |
| License | MIT |
| Platforms | linux, macos, windows |
| Tags | `clawk`, `setup`, `configuration`, `multi-agent`, `spawning`, `cli`, `gateway`, `bots`, `bot-mode`, `features`, `themes`, `skins`, `desktop-plugins`, `tui-widgets`, `petdex`, `development` |
| Related skills | [`claude-code`](../../bundled/autonomous-ai-agents/autonomous-ai-agents-claude-code.md), [`codex`](../../bundled/autonomous-ai-agents/autonomous-ai-agents-codex.md), [`opencode`](../../bundled/autonomous-ai-agents/autonomous-ai-agents-opencode.md) |

## Reference: full SKILL.md

:::info
The following is the complete skill definition that Clawksis loads when this skill is triggered. This is what the agent sees as instructions when the skill is active.
:::

# Clawksis

Clawksis is an open-source AI agent framework by Nous Research that runs in your terminal, a native desktop app, messaging platforms, and IDEs. It's in the same category as Claude Code (Anthropic), Codex (OpenAI), and OpenClaw — autonomous coding and task-execution agents that use tool calling to interact with your system. Clawksis works with any LLM provider (OpenRouter, Anthropic, OpenAI, Google, DeepSeek, xAI, local models, and 20+ others) and runs on Linux, macOS, Windows, and WSL.

What makes Clawksis different:

- **Self-improving through skills** — Clawksis learns from experience by saving reusable procedures as skills that load into future sessions.
- **Persistent memory across sessions** — remembers who you are, your preferences, environment details, and lessons learned. Pluggable memory backends.
- **Multi-platform gateway** — the same agent runs on Telegram, Discord, Slack, WhatsApp, iMessage, Signal, Matrix, Teams, Email, and a dozen more platforms with full tool access, not just chat.
- **Many surfaces** — the same agent core drives the CLI, the Ink TUI, a native Electron desktop app, a web dashboard, and an ACP server for IDEs (VS Code / Zed / JetBrains).
- **Provider-agnostic** — swap models and providers mid-workflow; credential pools rotate across multiple API keys automatically.
- **Profiles** — run multiple independent Clawksis instances with isolated configs, sessions, skills, and memory.

- **Extensible** — plugins, MCP servers, custom tools, webhook triggers, cron scheduling, and the full Python ecosystem.

People use Clawksis for software development, research, system administration, data analysis, content creation, home automation, and anything else that benefits from an AI agent with persistent context and full system access.

**This skill helps you work with Clawksis effectively** — setting it up, configuring features, spawning additional agent instances, troubleshooting issues, finding the right commands and settings, and understanding how the system works when you need to extend or contribute to it.

**Docs:** https://github.com/samuelgradientai-sys/clawksis-agent

## Quick Start

```bash
# Install (shell installer — bootstraps PM, Python, dependencies, and the launcher)
curl -fsSL https://raw.githubusercontent.com/samuelgradientai-sys/clawksis-agent/main/scripts/install.sh | bash

# Interactive chat (default surface; set display.interface: tui to launch the Ink TUI instead)
clawk

# Single query
clawk chat -q "What is the capital of France?"

# Setup wizard  /  pick model+provider  /  health check
clawk setup
clawk model
clawk doctor

# Other surfaces
clawk desktop                 # launch the native desktop app (alias: clawk gui)
clawk dashboard               # web admin panel + embedded chat
clawk proxy                   # OpenAI-compatible local proxy backed by your OAuth provider
```

## Key Paths

```
~/.clawksis/config.yaml       Main configuration (settings — never secrets)
~/.clawksis/.env              API keys and secrets ONLY (under $CLAWK_HOME if set)
$CLAWK_HOME/skills/        Installed skills
~/.clawksis/skins/            Custom themes (see references/themes.md)
~/.clawksis/desktop-plugins/  Desktop app UI plugins (see references/desktop-plugins.md)
~/.clawksis/tui-widgets/      TUI widget apps (see references/tui-widgets.md)
~/.clawksis/pets/             Installed pet mascots (see references/petdex.md)
~/.clawksis/state.db          Canonical session store (SQLite + FTS5)
~/.clawksis/sessions/         Gateway routing index, request dumps, *.jsonl transcripts
~/.clawksis/logs/             Gateway and error logs
~/.clawksis/auth.json         OAuth tokens and credential pools
~/.clawksis/clawksis-agent/     Source code (if git-installed)
```

Profiles use `~/.clawksis/profiles/<name>/` with the same layout. When a profile is active, resolve the real home from `$CLAWK_HOME` — never hardcode `~/.clawksis`.

## Routing Table — load the reference for the task

| User wants... | Load |
|---|---|
| **Anything not listed below — "can Clawksis do X?", "how do I set up X?"** | **https://samuelgradientai-sys.github.io/clawksis-agent/llms.txt** |
| Bots that chat, run routines, or message each other; the Bots tab | docs: `/user-guide/bot-mode` |
| CLI commands, subcommands, flags, "how do I run X" | `references/cli-reference.md` |
| In-session slash commands | `references/slash-commands.md` |
| Provider setup, API keys, OAuth | `references/providers-and-models.md` |
| config.yaml sections, toolsets, voice/STT/TTS | `references/configuration.md` |
| AGENTS.md / .clawk.md / CLAUDE.md project rules | `references/project-context-files.md` |
| Secret redaction, PII, approval modes, "reset permissions" | `references/security-privacy.md` |
| Delegation, cron, curator, kanban | `references/background-systems.md` |
| MCP servers (add, catalog, `clawk mcp`) | `references/native-mcp.md` |
| Webhook routes and event-driven runs | `references/webhooks.md` |
| A custom theme/skin ("synthwave theme", "change the gold ●") | `references/themes.md` + `templates/skin.yaml` |
| A desktop app UI element (pane, widget, ⌘K command, page) | `references/desktop-plugins.md` + `templates/plugin.js` |
| A live TUI panel or modal widget (ticker, clock, dashboard) | `references/tui-widgets.md` + `templates/clock.mjs` |
| Pet mascots — install, select, scale, diagnose | `references/petdex.md` |
| Windows-specific issues (keybinds, WinError 10106, BOM) | `references/windows-quirks.md` |
| Debugging: voice, tools missing, gateway, aux models | `references/troubleshooting.md` |
| Contributing code: adding tools, slash commands, tests | `references/contributor-guide.md` |
| delegate_task "capped at N" reports | `references/delegate-task-concurrency-diagnosis.md` |
| "Can app X use my Nous Portal subscription/OAuth?" | `references/portal-auth-for-third-party-apps.md` |
| Connecting a messaging platform (Telegram, Discord, Slack, WhatsApp, …) | docs: `/user-guide/messaging` |

The reference list above is not the feature list — it is the set of topics that
need more than their docs page. For everything else Clawksis ships, fetch
`llms.txt` and it maps the question to the page that answers it.

Two theming rules that hold even without loading the reference: **you apply skins yourself** (`clawk config set display.skin <name>` — every surface repaints live within ~a second; don't tell the user to run `/skin`), and **to tweak one color, edit the ACTIVE skin** (`clawk skin set <key> <hex>`) — never fork `default`, which drops the palette and resets the background.

## Spawning Additional Clawksis Instances

Run additional Clawksis processes as fully independent subprocesses — separate sessions, tools, and environments.

### When to Use This vs delegate_task

| | `delegate_task` | Spawning `clawk` process |
|-|-----------------|--------------------------|
| Isolation | Separate conversation, shared process | Fully independent process |
| Duration | Minutes (bounded by parent loop) | Hours/days |
| Tool access | Subset of parent's tools | Full tool access |
| Interactive | No | Yes (PTY mode) |
| Use case | Quick parallel subtasks | Long autonomous missions |

### One-Shot Mode

```
terminal(command="clawk chat -q 'Research GRPO papers and write summary to ~/research/grpo.md'", timeout=300)

# Background for long tasks:
terminal(command="clawk chat -q 'Set up CI/CD for ~/myapp'", background=true)
```

### Interactive PTY Mode (via tmux)

Clawksis uses prompt_toolkit, which requires a real terminal. Use tmux for interactive spawning:

```
# Start
terminal(command="tmux new-session -d -s agent1 -x 120 -y 40 'clawk'", timeout=10)

# Wait for startup, then send a message
terminal(command="sleep 8 && tmux send-keys -t agent1 'Build a FastAPI auth service' Enter", timeout=15)

# Read output
terminal(command="sleep 20 && tmux capture-pane -t agent1 -p", timeout=5)

# Send follow-up
terminal(command="tmux send-keys -t agent1 'Add rate limiting middleware' Enter", timeout=5)

# Exit
terminal(command="tmux send-keys -t agent1 '/exit' Enter && sleep 2 && tmux kill-session -t agent1", timeout=10)
```

### Multi-Agent Coordination

```
# Agent A: backend
terminal(command="tmux new-session -d -s backend -x 120 -y 40 'clawk -w'", timeout=10)
terminal(command="sleep 8 && tmux send-keys -t backend 'Build REST API for user management' Enter", timeout=15)

# Agent B: frontend
terminal(command="tmux new-session -d -s frontend -x 120 -y 40 'clawk -w'", timeout=10)
terminal(command="sleep 8 && tmux send-keys -t frontend 'Build React dashboard for user management' Enter", timeout=15)

# Check progress, relay context between them
terminal(command="tmux capture-pane -t backend -p | tail -30", timeout=5)
terminal(command="tmux send-keys -t frontend 'Here is the API schema from the backend agent: ...' Enter", timeout=5)
```

### Session Resume

```
# Resume most recent session
terminal(command="tmux new-session -d -s resumed 'clawk --continue'", timeout=10)

# Resume specific session
terminal(command="tmux new-session -d -s resumed 'clawk --resume 20260225_143052_a1b2c3'", timeout=10)
```

### Tips

- **Prefer `delegate_task` for quick subtasks** — less overhead than spawning a full process
- **Use `-w` (worktree mode)** when spawning agents that edit code — prevents git conflicts
- **Set timeouts** for one-shot mode — complex tasks can take 5-10 minutes
- **Use `clawk chat -q` for fire-and-forget** — no PTY needed
- **Use tmux for interactive sessions** — raw PTY mode has `\r` vs `\n` issues with prompt_toolkit
- **For scheduled tasks**, use the `cronjob` tool instead of spawning — handles delivery and retry

---

## Durable & Background Systems

Four systems run alongside the main conversation loop. Quick reference

here; full developer notes live in `AGENTS.md`, user-facing docs under

`website/docs/user-guide/features/`.

### Delegation (`delegate_task`)

Synchronous subagent spawn — the parent waits for the child's summary

before continuing its own loop. Isolated context + terminal session.

- **Single:** `delegate_task(goal, context, toolsets)`.

- **Batch:** `delegate_task(tasks=[{goal, ...}, ...])` runs children in

  parallel, capped by `delegation.max_concurrent_children` (default 3).

- **Roles:** `leaf` (default; cannot re-delegate) vs `orchestrator`

  (can spawn its own workers, bounded by `delegation.max_spawn_depth`).

- **Not durable.** If the parent is interrupted, the child is

  cancelled. For work that must outlive the turn, use `cronjob` or

  `terminal(background=True, notify_on_complete=True)`.

Config: `delegation.*` in `config.yaml`.

### Cron (scheduled jobs)

Durable scheduler — `cron/jobs.py` + `cron/scheduler.py`. Drive it via

the `cronjob` tool, the `clawk cron` CLI (`list`, `add`, `edit`,

`pause`, `resume`, `run`, `remove`), or the `/cron` slash command.

- **Schedules:** duration (`"30m"`, `"2h"`), "every" phrase

  (`"every monday 9am"`), 5-field cron (`"0 9 * * *"`), or ISO timestamp.

- **Per-job knobs:** `skills`, `model`/`provider` override, `script`

  (pre-run data collection; `no_agent=True` makes the script the whole

  job), `context_from` (chain job A's output into job B), `workdir`

  (run in a specific dir with its `AGENTS.md` / `CLAUDE.md` loaded),

  multi-platform delivery.

- **Invariants:** 3-minute hard interrupt per run, `.tick.lock` file

  prevents duplicate ticks across processes, cron sessions pass

  `skip_memory=True` by default, and cron deliveries are framed with a

  header/footer instead of being mirrored into the target gateway

  session (keeps role alternation intact).

User docs: https://github.com/samuelgradientai-sys/clawksis-agent

### Curator (skill lifecycle)

Background maintenance for agent-created skills. Tracks usage, marks

idle skills stale, archives stale ones, keeps a pre-run tar.gz backup

so nothing is lost.

- **CLI:** `clawk curator <verb>` — `status`, `run`, `pause`, `resume`,

  `pin`, `unpin`, `archive`, `restore`, `prune`, `backup`, `rollback`.

- **Slash:** `/curator <subcommand>` mirrors the CLI.

- **Scope:** only touches skills with `created_by: "agent"` provenance.

  Bundled + hub-installed skills are off-limits. **Never deletes** —

  max destructive action is archive. Pinned skills are exempt from

  every auto-transition and every LLM review pass.

- **Telemetry:** sidecar at `~/.clawksis/skills/.usage.json` holds

  per-skill `use_count`, `view_count`, `patch_count`,

  `last_activity_at`, `state`, `pinned`.

Config: `curator.*` (`enabled`, `interval_hours`, `min_idle_hours`,

`stale_after_days`, `archive_after_days`, `backup.*`).

User docs: https://github.com/samuelgradientai-sys/clawksis-agent

### Kanban (multi-agent work queue)

Durable SQLite board for multi-profile / multi-worker collaboration.

Users drive it via `clawk kanban <verb>`; dispatcher-spawned workers

see a focused `kanban_*` toolset gated by `CLAWK_KANBAN_TASK`, and

orchestrator profiles can opt into the broader `kanban` toolset. Normal

sessions still have zero `kanban_*` schema footprint unless configured.

- **CLI verbs (common):** `init`, `create`, `list` (alias `ls`),

  `show`, `assign`, `link`, `unlink`, `comment`, `complete`, `block`,

  `unblock`, `archive`, `tail`. Less common: `watch`, `stats`, `runs`,

  `log`, `dispatch`, `daemon`, `gc`.

- **Worker/orchestrator toolset:** `kanban_show`, `kanban_complete`,

  `kanban_block`, `kanban_heartbeat`, `kanban_comment`, `kanban_create`,

  `kanban_link`; profiles that explicitly enable the `kanban` toolset

  outside a dispatcher-spawned task also get `kanban_list` and

  `kanban_unblock` for board routing.

- **Dispatcher** runs inside the gateway by default

  (`kanban.dispatch_in_gateway: true`) — reclaims stale claims,

  promotes ready tasks, atomically claims, spawns assigned profiles.

  Auto-blocks a task after `failure_limit` consecutive spawn failures

  (default 2; configurable via `kanban.failure_limit` or per-task

  `max_retries`).

- **Isolation:** board is the hard boundary (workers get

  `CLAWK_KANBAN_BOARD` pinned in env); tenant is a soft namespace

  within a board for workspace-path + memory-key isolation.

User docs: https://github.com/samuelgradientai-sys/clawksis-agent

---

## Windows-Specific Quirks

Clawksis runs natively on Windows (PowerShell, cmd, Windows Terminal, git-bash

mintty, VS Code integrated terminal). Most of it just works, but a handful

of differences between Win32 and POSIX have bitten us — document new ones

here as you hit them so the next person (or the next session) doesn't

rediscover them from scratch.

### Input / Keybindings

**Alt+Enter doesn't insert a newline.** Windows Terminal intercepts Alt+Enter

at the terminal layer to toggle fullscreen — the keystroke never reaches

prompt_toolkit. Use **Ctrl+Enter** instead. Windows Terminal delivers

Ctrl+Enter as LF (`c-j`), distinct from plain Enter (`c-m` / CR), and the

CLI binds `c-j` to newline insertion on `win32` only (see

`_bind_prompt_submit_keys` + the Windows-only `c-j` binding in `cli.py`).

Side effect: the raw Ctrl+J keystroke also inserts a newline on Windows —

unavoidable, because Windows Terminal collapses Ctrl+Enter and Ctrl+J to

the same keycode at the Win32 console API layer. No conflicting binding

existed for Ctrl+J on Windows, so this is a harmless side effect.

mintty / git-bash behaves the same (fullscreen on Alt+Enter) unless you

disable Alt+Fn shortcuts in Options → Keys. Easier to just use Ctrl+Enter.

**Diagnosing keybindings.** Run `python scripts/keystroke_diagnostic.py`

(repo root) to see exactly how prompt_toolkit identifies each keystroke

in the current terminal. Answers questions like "does Shift+Enter come

through as a distinct key?" (almost never — most terminals collapse it

to plain Enter) or "what byte sequence is my terminal sending for

Ctrl+Enter?" This is how the Ctrl+Enter = c-j fact was established.

### Config / Files

**HTTP 400 "No models provided" on first run.** `config.yaml` was saved

with a UTF-8 BOM (common when Windows apps write it). Re-save as UTF-8

without BOM. `clawk config edit` writes without BOM; manual edits in

Notepad are the usual culprit.

### `execute_code` / Sandbox

**WinError 10106** ("The requested service provider could not be loaded

or initialized") from the sandbox child process — it can't create an

`AF_INET` socket, so the loopback-TCP RPC fallback fails before

`connect()`. Root cause is usually **not** a broken Winsock LSP; it's

Clawksis's own env scrubber dropping `SYSTEMROOT` / `WINDIR` / `COMSPEC`

from the child env. Python's `socket` module needs `SYSTEMROOT` to locate

`mswsock.dll`. Fixed via the `_WINDOWS_ESSENTIAL_ENV_VARS` allowlist in

`tools/code_execution_tool.py`. If you still hit it, echo `os.environ`

inside an `execute_code` block to confirm `SYSTEMROOT` is set. Full

diagnostic recipe in `references/execute-code-sandbox-env-windows.md`.

### Testing / Contributing

**`scripts/run_tests.sh` doesn't work as-is on Windows** — it looks for

POSIX venv layouts (`.venv/bin/activate`). The Clawksis-installed venv at

`venv/Scripts/` has no pip or pytest either (stripped for install size).

Workaround: install `pytest + pytest-xdist + pyyaml` into a system Python

3.11 user site, then invoke pytest directly with `PYTHONPATH` set:

```bash

"/c/Program Files/Python311/python" -m pip install --user pytest pytest-xdist pyyaml

export PYTHONPATH="$(pwd)"

"/c/Program Files/Python311/python" -m pytest tests/foo/test_bar.py -v --tb=short -n 0

```

Use `-n 0`, not `-n 4` — `pyproject.toml`'s default `addopts` already

includes `-n`, and the wrapper's CI-parity guarantees don't apply off POSIX.

**POSIX-only tests need skip guards.** Common markers already in the codebase:

- Symlinks — elevated privileges on Windows

- `0o600` file modes — POSIX mode bits not enforced on NTFS by default

- `signal.SIGALRM` — Unix-only (see `tests/conftest.py::_enforce_test_timeout`)

- Winsock / Windows-specific regressions — `@pytest.mark.skipif(sys.platform != "win32", ...)`

Use the existing skip-pattern style (`sys.platform == "win32"` or

`sys.platform.startswith("win")`) to stay consistent with the rest of the

suite.

### Path / Filesystem

**Line endings.** Git may warn `LF will be replaced by CRLF the next time

Git touches it`. Cosmetic — the repo's `.gitattributes` normalizes. Don't

let editors auto-convert committed POSIX-newline files to CRLF.

**Forward slashes work almost everywhere.** `C:/Users/...` is accepted by

every Clawksis tool and most Windows APIs. Prefer forward slashes in code

and logs — avoids shell-escaping backslashes in bash.

---

## Troubleshooting

### Voice not working

1. Check `stt.enabled: true` in config.yaml

2. Verify provider: `pip install faster-whisper` or set API key

3. In gateway: `/restart`. In CLI: exit and relaunch.

### Tool not available

1. `clawk tools` — check if toolset is enabled for your platform

2. Some tools need env vars (check `.env`)

3. `/reset` after enabling tools

### Model/provider issues

1. `clawk doctor` — check config and dependencies

2. `clawk auth` — re-authenticate OAuth providers (or `clawk auth add <provider>`)

3. Check `.env` has the right API key

4. **Copilot 403**: `gh auth login` tokens do NOT work for Copilot API. You must use the Copilot-specific OAuth device code flow via `clawk model` → GitHub Copilot.

### Changes not taking effect

- **Tools/skills:** `/reset` starts a new session with updated toolset

- **Config changes:** In gateway: `/restart`. In CLI: exit and relaunch.

- **Code changes:** Restart the CLI or gateway process

### Skills not showing

1. `clawk skills list` — verify installed

2. `clawk skills config` — check platform enablement

3. Load explicitly: `/skill name` or `clawk -s name`

### Gateway issues

Check logs first:

```bash

grep -i "failed to send\|error" ~/.clawksis/logs/gateway.log | tail -20

```

Common gateway problems:

- **Gateway dies on SSH logout**: Enable linger: `sudo loginctl enable-linger $USER`

- **Gateway dies on WSL2 close**: WSL2 requires `systemd=true` in `/etc/wsl.conf` for systemd services to work. Without it, gateway falls back to `nohup` (dies when session closes).

- **Gateway crash loop**: Reset the failed state: `systemctl --user reset-failed clawk-gateway`

### Platform-specific issues

- **Discord bot silent**: Must enable **Message Content Intent** in Bot → Privileged Gateway Intents.

- **Slack bot only works in DMs**: Must subscribe to `message.channels` event. Without it, the bot ignores public channels.

- **Windows-specific issues** (`Alt+Enter` newline, WinError 10106, UTF-8 BOM config, test suite, line endings): see the dedicated **Windows-Specific Quirks** section above.

### Auxiliary models not working

If `auxiliary` tasks (vision, compression, session_search) fail silently, the `auto` provider can't find a backend. Either set `OPENROUTER_API_KEY` or `GOOGLE_API_KEY`, or explicitly configure each auxiliary task's provider:

```bash

clawk config set auxiliary.vision.provider <your_provider>

clawk config set auxiliary.vision.model <model_name>

```

---

## Where to Find Things

| Looking for... | Location |

|----------------|----------|

| Config options | `clawk config edit` or [Configuration docs](https://github.com/samuelgradientai-sys/clawksis-agent |

| Available tools | `clawk tools list` or [Tools reference](https://github.com/samuelgradientai-sys/clawksis-agent |

| Slash commands | `/help` in session or [Slash commands reference](https://github.com/samuelgradientai-sys/clawksis-agent |

| Skills catalog | `clawk skills browse` or [Skills catalog](https://github.com/samuelgradientai-sys/clawksis-agent |

| Provider setup | `clawk model` or [Providers guide](https://github.com/samuelgradientai-sys/clawksis-agent |

| Platform setup | `clawk gateway setup` or [Messaging docs](https://github.com/samuelgradientai-sys/clawksis-agent |

| MCP servers | `clawk mcp list` or [MCP guide](https://github.com/samuelgradientai-sys/clawksis-agent |

| Profiles | `clawk profile list` or [Profiles docs](https://github.com/samuelgradientai-sys/clawksis-agent |

| Cron jobs | `clawk cron list` or [Cron docs](https://github.com/samuelgradientai-sys/clawksis-agent |

| Memory | `clawk memory status` or [Memory docs](https://github.com/samuelgradientai-sys/clawksis-agent |

| Env variables | `clawk config env-path` or [Env vars reference](https://github.com/samuelgradientai-sys/clawksis-agent |

| CLI commands | `clawk --help` or [CLI reference](https://github.com/samuelgradientai-sys/clawksis-agent |

| Gateway logs | `~/.clawksis/logs/gateway.log` |

| Session files | `clawk sessions browse` (reads state.db) |

| Source code | `~/.clawksis/clawksis-agent/` |

---

## Contributor Quick Reference

For occasional contributors and PR authors. Full developer docs: https://github.com/samuelgradientai-sys/clawksis-agent

### Project Layout

<!-- ascii-guard-ignore -->
```

clawksis-agent/

├── run_agent.py          # AIAgent — core conversation loop

├── model_tools.py        # Tool discovery and dispatch

├── toolsets.py           # Toolset definitions

├── cli.py                # Interactive CLI (ClawksisCLI)

├── clawk_state.py       # SQLite session store

├── agent/                # Prompt builder, context compression, memory, model routing, credential pooling, skill dispatch

├── clawk_cli/           # CLI subcommands, config, setup, commands

│   ├── commands.py       # Slash command registry (CommandDef)

│   ├── config.py         # DEFAULT_CONFIG, env var definitions

│   └── main.py           # CLI entry point and argparse

├── tools/                # One file per tool

│   └── registry.py       # Central tool registry

├── gateway/              # Messaging gateway

│   └── platforms/        # Platform adapters (telegram, discord, etc.)

├── cron/                 # Job scheduler

├── tests/                # ~3000 pytest tests

└── website/              # Docusaurus docs site

```
<!-- ascii-guard-ignore-end -->

Config: `~/.clawksis/config.yaml` (settings), `~/.clawksis/.env` (API keys).

### Adding a Tool (3 files)

**1. Create `tools/your_tool.py`:**

```python
import json, os

from tools.registry import registry

def check_requirements() -> bool:

    return bool(os.getenv("EXAMPLE_API_KEY"))

def example_tool(param: str, task_id: str = None) -> str:

    return json.dumps({"success": True, "data": "..."})

registry.register(
    name="example_tool",
    toolset="example",
    schema={"name": "example_tool", "description": "...", "parameters": {...}},
    handler=lambda args, **kw: example_tool(
        param=args.get("param", ""), task_id=kw.get("task_id")
    ),
    check_fn=check_requirements,
    requires_env=["EXAMPLE_API_KEY"],
)
```

**2. Add to `toolsets.py`** → `_CLAWK_CORE_TOOLS` list.

Auto-discovery: any `tools/*.py` file with a top-level `registry.register()` call is imported automatically — no manual list needed.

All handlers must return JSON strings. Use `get_clawk_home()` for paths, never hardcode `~/.clawksis`.

### Adding a Slash Command

1. Add `CommandDef` to `COMMAND_REGISTRY` in `clawk_cli/commands.py`

2. Add handler in `cli.py` → `process_command()`

3. (Optional) Add gateway handler in `gateway/run.py`

All consumers (help text, autocomplete, Telegram menu, Slack mapping) derive from the central registry automatically.

### Agent Loop (High Level)

```

run_conversation():

  1. Build system prompt

  2. Loop while iterations < max:

     a. Call LLM (OpenAI-format messages + tool schemas)

     b. If tool_calls → dispatch each via handle_function_call() → append results → continue

     c. If text response → return

  3. Context compression triggers automatically near token limit

```

### Testing

```bash

python -m pytest tests/ -o 'addopts=' -q   # Full suite

python -m pytest tests/tools/ -q            # Specific area

```

- Tests auto-redirect `CLAWK_HOME` to temp dirs — never touch real `~/.clawksis/`

- Run full suite before pushing any change

- Use `-o 'addopts='` to clear any baked-in pytest flags

**Windows contributors:** `scripts/run_tests.sh` currently looks for POSIX venvs (`.venv/bin/activate` / `venv/bin/activate`) and will error out on Windows where the layout is `venv/Scripts/activate` + `python.exe`. The Clawksis-installed venv at `venv/Scripts/` also has no `pip` or `pytest` — it's stripped for end-user install size. Workaround: install pytest + pytest-xdist + pyyaml into a system Python 3.11 user site (`/c/Program Files/Python311/python -m pip install --user pytest pytest-xdist pyyaml`), then run tests directly:

```bash

export PYTHONPATH="$(pwd)"

"/c/Program Files/Python311/python" -m pytest tests/tools/test_foo.py -v --tb=short -n 0

```

Use `-n 0` (not `-n 4`) because `pyproject.toml`'s default `addopts` already includes `-n`, and the wrapper's CI-parity story doesn't apply off-POSIX.

**Cross-platform test guards:** tests that use POSIX-only syscalls need a skip marker. Common ones already in the codebase:

- Symlink creation → `@pytest.mark.skipif(sys.platform == "win32", reason="Symlinks require elevated privileges on Windows")` (see `tests/cron/test_cron_script.py`)

- POSIX file modes (0o600, etc.) → `@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX mode bits not enforced on Windows")` (see `tests/clawk_cli/test_auth_toctou_file_modes.py`)

- `signal.SIGALRM` → Unix-only (see `tests/conftest.py::_enforce_test_timeout`)

- Live Winsock / Windows-specific regression tests → `@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific regression")`

**Monkeypatching `sys.platform` is not enough** when the code under test also calls `platform.system()` / `platform.release()` / `platform.mac_ver()`. Those functions re-read the real OS independently, so a test that sets `sys.platform = "linux"` on a Windows runner will still see `platform.system() == "Windows"` and route through the Windows branch. Patch all three together:

```python
monkeypatch.setattr(sys, "platform", "linux")

monkeypatch.setattr(platform, "system", lambda: "Linux")

monkeypatch.setattr(platform, "release", lambda: "6.8.0-generic")
```

See `tests/agent/test_prompt_builder.py::TestEnvironmentHints` for a worked example.

### Extending the system prompt's execution-environment block

Factual guidance about the host OS, user home, cwd, terminal backend, and shell (bash vs. PowerShell on Windows) is emitted from `agent/prompt_builder.py::build_environment_hints()`. This is also where the WSL hint and per-backend probe logic live. The convention:

- **Local terminal backend** → emit host info (OS, `$HOME`, cwd) + Windows-specific notes (hostname ≠ username, `terminal` uses bash not PowerShell).

- **Remote terminal backend** (anything in `_REMOTE_TERMINAL_BACKENDS`: `docker, singularity, modal, daytona, ssh, managed_modal`) → **suppress** host info entirely and describe only the backend. A live `uname`/`whoami`/`pwd` probe runs inside the backend via `tools.environments.get_environment(...).execute(...)`, cached per process in `_BACKEND_PROBE_CACHE`, with a static fallback if the probe times out.

- **Key fact for prompt authoring:** when `TERMINAL_ENV != "local"`, *every* file tool (`read_file`, `write_file`, `patch`, `search_files`) runs inside the backend container, not on the host. The system prompt must never describe the host in that case — the agent can't touch it.

Full design notes, the exact emitted strings, and testing pitfalls:

`references/prompt-builder-environment-hints.md`.

**Refactor-safety pattern (POSIX-equivalence guard):** when you extract inline logic into a helper that adds Windows/platform-specific behavior, keep a `_legacy_<name>` oracle function in the test file that's a verbatim copy of the old code, then parametrize-diff against it. Example: `tests/tools/test_code_execution_windows_env.py::TestPosixEquivalence`. This locks in the invariant that POSIX behavior is bit-for-bit identical and makes any future drift fail loudly with a clear diff.

### Commit Conventions

```

type: concise subject line

Optional body.

```

Types: `fix:`, `feat:`, `refactor:`, `docs:`, `chore:`

### Key Rules

- **Never break prompt caching** — don't change context, tools, or system prompt mid-conversation

- **Message role alternation** — never two assistant or two user messages in a row

- Use `get_clawk_home()` from `clawk_constants` for all paths (profile-safe)

- Config values go in `config.yaml`, secrets go in `.env`

- New tools need a `check_fn` so they only appear when requirements are met
