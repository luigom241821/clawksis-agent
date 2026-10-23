# Clawksis CLI Reference

Live sources when anything looks stale: `clawk --help`, `clawk <command> --help`,
https://clawksis-agent.nousresearch.com/docs/reference/cli-commands

### Global Flags

```
clawk [flags] [command]        (no subcommand = interactive chat)

  --version, -V             Show version
  -z, --oneshot PROMPT      One-shot: print ONLY the final response (for scripts/pipes)
  -m MODEL  --provider P    Model/provider override for this invocation
  -t, --toolsets LIST       Comma-separated toolsets for this invocation
  --resume, -r SESSION      Resume session by ID or title
  --continue, -c [NAME]     Resume by name, or most recent session
  --worktree, -w            Isolated git worktree mode (parallel agents)
  --skills, -s SKILL        Preload skills (comma-separate or repeat)
  --profile, -p NAME        Use a named profile
  --yolo                    Skip dangerous command approval
  --tui / --cli             Force the Ink TUI / classic REPL
  --ignore-rules            Skip AGENTS.md/SOUL.md/memory/skill injection
  --safe-mode               Disable ALL customizations (troubleshooting)
  --pass-session-id         Include session ID in system prompt
```

### Chat

```
clawk chat [flags]
  -q, --query TEXT          Single query, non-interactive
  --image PATH              Attach a local image to a single query
  -Q, --quiet               Suppress banner, spinner, tool previews
  --checkpoints             Enable filesystem checkpoints (/rollback)
  --max-turns N             Cap tool-calling iterations
  --source TAG              Session source tag (default: cli)
```
(plus the global flags above)

### Configuration

```
clawk setup [section]      Wizard (model|tts|terminal|gateway|tools|agent)
clawk model                Interactive model/provider picker
clawk fallback [add|remove|list]  Fallback provider chain
clawk config [show|edit|get|set|unset|path|env-path|check|migrate]
clawk login / logout       OAuth sign-in / clear stored auth
clawk doctor [--fix]       Check dependencies and config
clawk status [--full]      Component summary (--full: every section)
```

### Tools & Skills

```
clawk tools [list|enable NAME|disable NAME]   Per-platform toolsets (curses UI with no args)

clawk skills list|browse|search QUERY|inspect ID
clawk skills install ID    Hub identifier OR a direct https://…/SKILL.md URL
clawk skills config        Enable/disable skills per platform
clawk skills check|update|uninstall|publish PATH
clawk skills tap add REPO  Add a GitHub repo as a skill source
clawk bundles              Skill bundles (one /<name> alias loads several skills)
```

### MCP Servers

```
clawk mcp add NAME (--url or --command) | remove | list | test NAME
clawk mcp catalog | install NAME     Curated catalog install
clawk mcp configure NAME             Toggle tool selection
clawk mcp-serve                      Run Clawksis as an MCP server (mcp-serve plugin)
```
Details (transport, tool discovery, catalog): `references/native-mcp.md`.

### Gateway (Messaging Platforms)

```
clawk gateway run|install|start|stop|restart|status|setup
```

20+ platforms: Telegram, Discord, Slack, WhatsApp (Baileys + Business Cloud API), iMessage (Photon — `clawk photon setup`), Signal, Email, SMS, Matrix, Mattermost, Teams, LINE, SimpleX, ntfy, Google Chat, Home Assistant, DingTalk, Feishu, WeCom, Weixin, API Server, Webhooks. Open WebUI connects via the API Server adapter. Most adapters ship under `plugins/platforms/`.
Docs: https://clawksis-agent.nousresearch.com/docs/user-guide/messaging/

### Sessions

```
clawk sessions list|browse|rename ID TITLE|delete ID|export OUT|prune|stats
```

### Cron / Webhooks

```
clawk cron list|create SCHED|edit ID|pause|resume|run ID|remove|status
    Schedules: '30m', 'every 2h', '0 9 * * *', ISO timestamp
clawk webhook subscribe NAME|list|remove NAME|test NAME
```
Webhook payloads/routes: `references/webhooks.md`.

### Profiles

```
clawk profile list|create NAME (--clone|--clone-all|--clone-from)|use|show|delete
clawk profile rename A B | alias NAME | export NAME | import FILE
clawk profile migrate-identity A B   Retry a completed rename's session/routing identity migration
```

### Credentials & Pools

```
clawk auth                 Interactive credential manager
clawk auth add [PROVIDER]  Add OAuth or API-key credential (nous, openai-codex, qwen-oauth, …)
clawk auth list|remove P IDX|reset PROVIDER|status
```
Multiple credentials per provider form a pool that rotates automatically and skips exhausted keys.

### Other

```
clawk desktop / gui        Native desktop app
clawk dashboard            Web admin panel + embedded chat (--stop / --status)
clawk proxy                OpenAI-compatible local proxy backed by an OAuth provider
clawk portal               Quick setup / sign in via Nous Portal
clawk kanban <verb>        Multi-agent work-queue board
clawk project              Named multi-folder workspaces
clawk skin list|use|set    Switch/tweak skins (see references/themes.md)
clawk pets <verb>          Pet mascots (see references/petdex.md)
clawk memory setup|status|off|reset   Memory provider
clawk secrets bitwarden|onepassword   External secret stores
clawk moa                  Mixture-of-Agents slots
clawk hooks / security / backup / import / checkpoints / console
clawk logs [-f] [errors]   View agent/error logs
clawk send                 One-off message through a gateway platform
clawk pairing / plugins / insights / journey / computer-use
clawk acp                  ACP server (IDE integration)
clawk completion bash|zsh|fish
clawk update / uninstall
```

Plugin- and provider-supplied subcommands (e.g. `clawk photon setup`) only appear once their plugin is installed/active. Importing from OpenClaw, Claude Code, Codex CLI or Cursor (`clawk import-agent <agent>`, plus the older `clawk claw migrate|cleanup`) comes from the `agent-importers` plugin; a fresh `clawk setup` that finds one of those agents offers to install it.

### Where to Find Things

| Looking for... | Location |
|---|---|
| Config options | `clawk config edit` · [Configuration docs](https://clawksis-agent.nousresearch.com/docs/user-guide/configuration) |
| Tools / toolsets | `clawk tools list` · [Tools reference](https://clawksis-agent.nousresearch.com/docs/reference/tools-reference) |
| Skills catalog | `clawk skills browse` · [Skills catalog](https://clawksis-agent.nousresearch.com/docs/reference/skills-catalog) |
| Provider setup | `clawk model` · [Providers guide](https://clawksis-agent.nousresearch.com/docs/integrations/providers) |
| Env variables | `clawk config env-path` · [Env vars reference](https://clawksis-agent.nousresearch.com/docs/reference/environment-variables) |
| Gateway logs | `~/.clawksis/logs/gateway.log` (or `clawk logs`) |
| Sessions | `clawk sessions browse` (reads state.db) |
