---
sidebar_position: 4
---

# Running Many Gateways at Once

Operate multiple [profiles](./profiles.md) — each with its own bot tokens,
sessions, and memory — as managed services on a single machine. This page
covers the operational concerns: starting them all together, viewing logs
across profiles, preventing the host from sleeping, and recovering from common
launchd/systemd quirks.

If you only run one Clawksis agent, you don't need this page — see
[Profiles](./profiles.md) for the basics. And if your instances live on
*different* machines that one desktop app should reach simultaneously, see
[Connecting Desktop to Many Clawksis Instances](./multi-connection-desktop.md).

## When to use this


You want this setup when you have two or more Clawksiss that should all
be online at the same time. Common reasons:

- A personal assistant on one Telegram bot and a coding agent on another
- One agent per family member or one per Slack workspace
- Sandbox + production instances of the same configuration
- A research agent + a writing agent + a cron-driven bot — each with isolated
  memory and skills

Every profile already gets its own per-platform supervisor entry: a LaunchAgent
(`ai.clawk.gateway-<name>.plist`), a systemd user service
(`clawk-gateway-<name>.service`), a systemd **system** service when installed with
`sudo clawk gateway install --system` (runs as the invoking user via `User=`), a
Windows Scheduled Task, or an s6/Docker service — and the Desktop app spawns its own
per-profile `clawk serve` backend. This guide adds the patterns for managing them
collectively.

## Quick start

```bash
# Create profiles (once)
clawk profile create coder
clawk profile create personal-bot
clawk profile create research

# Configure each
coder setup
personal-bot setup
research setup

# Install each gateway as a managed service
coder gateway install
personal-bot gateway install
research gateway install

# Start them all
coder gateway start
personal-bot gateway start
research gateway start
```

That's it — three independent agents, each on its own process, restarting
automatically on crash and on user login.

## Start, stop, or restart all gateways at once

The CLI ships with single-profile lifecycle commands. To act across every
profile, wrap them in a shell loop. Put the snippet below in
`~/.local/bin/clawk-gateways` and `chmod +x` it:

```sh
#!/bin/sh
set -eu

# Add or remove profile names here as you create / delete profiles.
profiles="default coder personal-bot research"

usage() {
  echo "Usage: clawk-gateways {start|stop|restart|status|list}"
}

run_for_profile() {
  profile="$1"
  action="$2"
  if [ "$profile" = "default" ]; then
    clawk gateway "$action"
  else
    clawk -p "$profile" gateway "$action"
  fi
}

action="${1:-}"
case "$action" in
  start|stop|restart|status)
    for profile in $profiles; do
      echo "==> $action $profile"
      run_for_profile "$profile" "$action"
    done
    ;;
  list)
    clawk gateway list
    ;;
  *)
    usage
    exit 2
    ;;
esac
```

Then:

```bash
clawk-gateways start      # start every configured profile
clawk-gateways stop       # stop every configured profile
clawk-gateways restart    # restart all
clawk-gateways status     # status across all
clawk-gateways list       # delegates to `clawk gateway list`
```

:::tip
The `default` profile is targeted with `clawk gateway <action>` (no `-p`),
not `clawk -p default gateway <action>`. The wrapper above handles both forms.
:::

## Manage one profile

The shortcut commands every profile installs:

```bash
coder gateway run        # foreground (Ctrl-C to stop)
coder gateway start      # start the managed service
coder gateway stop       # stop the managed service
coder gateway restart    # restart
coder gateway status     # status
coder gateway install    # create the LaunchAgent / systemd unit
coder gateway uninstall  # remove the service file
```

These are equivalent to `clawk -p coder gateway <action>` — useful if a
profile alias is not on `PATH` or if you target profiles dynamically from a
script.

## Service files

Each profile installs its own service with a unique name, so installations
never clash:

| Platform | Path                                                              |
| -------- | ----------------------------------------------------------------- |
| macOS    | `~/Library/LaunchAgents/ai.clawk.gateway-<profile>.plist`        |
| Linux    | `~/.config/systemd/user/clawk-gateway-<profile>.service`         |

The default profile keeps the historical names: `ai.clawk.gateway.plist` /
`clawk-gateway.service`.

## Viewing logs

Each profile writes to its own log files:

```bash
# Default profile
tail -f ~/.clawksis/logs/gateway.log
tail -f ~/.clawksis/logs/gateway.error.log

# Named profile
tail -f ~/.clawksis/profiles/<name>/logs/gateway.log
tail -f ~/.clawksis/profiles/<name>/logs/gateway.error.log
```

Stream every profile's log simultaneously:

```bash
tail -f ~/.clawksis/logs/gateway.log ~/.clawksis/profiles/*/logs/gateway.log
```

The CLI also has a structured log viewer:

```bash

clawk logs --tail              # follow default profile

clawk -p coder logs --tail     # follow one profile
clawk logs --help              # filters, levels, JSON output
```

## Identify what's actually running

```bash
clawk profile list             # profiles + model + gateway state
clawk-gateways status          # full status across every profile
launchctl list | grep clawk    # macOS — PIDs and labels
systemctl --user list-units 'clawk-gateway-*'   # Linux — units
```

## Editing configuration

Every profile keeps its config inside its own directory:

```
~/.clawksis/profiles/<name>/
├── .env              # API keys, bot tokens (chmod 600)
├── config.yaml       # model, provider, toolsets, gateway settings
└── SOUL.md           # personality / system prompt
```

The default profile uses `~/.clawksis/` directly with the same three files.

Edit them with any editor or via the CLI:

```bash
clawk config set model.model anthropic/claude-sonnet-4    # default profile
coder config set model.model openai/gpt-5                  # named profile
```

After editing `.env` or `config.yaml`, restart the affected gateway:

```bash
coder gateway restart
# or, for everything:
clawk-gateways restart
```

## Keeping the host awake

The gateway process can run all day, but the operating system will still try
to sleep when idle. Two patterns:

### macOS — `caffeinate`

`caffeinate` is built into macOS and prevents sleep while it runs. No install.

```bash
caffeinate -dis                    # block display, idle, and system sleep
caffeinate -dis -t 28800           # same, auto-exit after 8 hours
caffeinate -i -w $(cat ~/.clawksis/gateway.pid) &   # awake while default gateway runs

# Persistent: run in background and forget
nohup caffeinate -dis >/dev/null 2>&1 &
disown

# Inspect / stop
pmset -g assertions | grep -iE 'caffeinate|prevent|user is active'
pkill caffeinate
```

| Flag   | Effect                                            |
| ------ | ------------------------------------------------- |
| `-d`   | block display sleep                               |
| `-i`   | block idle system sleep (default)                 |
| `-m`   | block disk sleep                                  |
| `-s`   | block system sleep (AC-powered Macs only)         |
| `-u`   | simulate user activity (prevents screen lock)     |
| `-t N` | auto-exit after `N` seconds                       |
| `-w P` | exit when PID `P` exits                           |

:::warning Lid-close still sleeps the Mac
`caffeinate` cannot override the hardware-driven lid-close sleep on MacBooks.
For lid-closed operation, change your Energy Saver / Battery preferences or
use a third-party tool.
:::

### Linux — `systemd-inhibit` or `loginctl`

```bash
# Inhibit suspend while a command runs
systemd-inhibit --what=idle:sleep --who=clawk --why="gateways running" \
  sleep infinity &

# Allow user services to keep running after logout (recommended)
sudo loginctl enable-linger "$USER"
```

After enabling lingering, your systemd user units (including
`clawk-gateway-<profile>.service`) continue running across SSH disconnects
and reboots.

## Token-conflict safety

Each profile must use unique bot tokens for each platform. If two profiles
share a Telegram, Discord, Slack, WhatsApp, or Signal token, the second
gateway refuses to start with an error naming the conflicting profile. Under
[multiplexing](#alternative-one-gateway-for-all-profiles-multiplexing) the same
rule parks only the duplicate profile's adapter and the shared gateway keeps
running.

To audit:

```bash
grep -H 'TELEGRAM_BOT_TOKEN\|DISCORD_BOT_TOKEN' \
     ~/.clawksis/.env ~/.clawksis/profiles/*/.env
```

## Migrating from per-profile gateways

If your profiles each run their own gateway today (one systemd unit or launchd
agent per profile, from a release before multiplex-only), the default gateway's
boot preflight keeps it standalone until they are folded (the unset default
never double-binds a running fleet). `clawk update` folds them for you unless a
real boundary blocks it (below); the same fold is one command, and re-running it
on a half-migrated host (flag on, a unit left behind, a crash between the two)
finishes the job instead of reporting "already multiplexed":

```bash
clawk gateway migrate --multiplex --dry-run   # print the plan and any blockers; changes nothing
clawk gateway migrate --multiplex             # apply (asks for confirmation on a TTY; -y skips)
```

There is no `--standalone` reverse command: a per-profile fleet is not a
supported target. A blocked fleet keeps running as it is, and each profile
keeps `clawk -p <name> gateway install --force` as its path — or opts out of
the host gateway with `gateway.standalone: true` (see
[No new per-profile gateways](#no-new-per-profile-gateways)), which
`clawk gateway migrate --multiplex` respects.

### Docker / Clawksis Cloud (s6-supervised container)

Inside the official image every profile has an s6 slot
(`/run/service/gateway-<profile>`). The container's boot registers every *named*
slot down and folds its autostart intent into the root slot, so a fresh boot
already multiplexes. An **in-place** update no longer needs a container restart
to converge either: `clawk gateway migrate --multiplex` (and the hook `clawk
update` runs) parks any named slot that is still up (`s6-svc -d` plus a `down`
file so a supervisor restart does not revive it), folds its intent into the root
slot through the same rule the boot uses, and restarts the root slot. A
registered-down slot is never a blocker — only a slot that is actually up is.
The one thing the command still cannot do from inside is create a root slot the
boot never registered; that case names itself and asks for a container restart.

### What `clawk update` does

After a successful update, when the install has two or more profiles, at least
one secondary profile runs its own gateway (a live process or an installed
service) and `gateway.multiplex_profiles` is off, `clawk update` runs the same
preflight:

- **Nothing blocks it** → the migration runs automatically (the same code path
  as `clawk gateway migrate --multiplex --yes`) and prints what it did. This
  is deterministic and never prompts, so it also runs on headless/cron updates.
- **Something blocks it** → a warning block lists each blocker with its exact
  fix and the one-liner to run later. Nothing is changed.

Single-profile installs are never migrated (there is nothing to gain), and an
install that is already multiplexing is left alone. `clawk update` also does
nothing when no secondary profile runs its own gateway — it never flips modes
on an install where nothing was running.

### Boundaries `clawk update` never crosses on its own

The unattended hook only folds profiles that share **one UNIX user, one service
domain and one `profiles/` tree** — the shape `clawk profile create` produces.
A standalone secondary behind any of these boundaries stops the automatic path:

| boundary | example |
|---|---|
| different service manager or scope | default on user systemd, a secondary on **system** systemd (or launchd), or the default detached with a service-managed secondary |
| more than one installed unit on a profile | a user **and** a system unit for the same profile (the explicit command removes both) |
| different UNIX user | a system unit with its own `User=`, or a live gateway owned by another uid; a system unit whose `User=` this host cannot resolve — on the secondary **or** on the default — counts as unknown, never as "same user" |
| `CLAWK_HOME` outside `<default home>/profiles/` | a unit pinning `CLAWK_HOME=/opt/clawksis/profiles/emma` |

In that case `clawk update` prints the boundary it found plus
`clawk gateway migrate --multiplex`, and changes nothing — no unit is removed
and the per-profile gateways keep running (`--force` remains their path where
a boundary like these blocks the fold; a profile free of them opts out with
`gateway.standalone: true`). Collapsing such a fleet replaces a
kernel-enforced boundary (file ownership, `User=`) with in-process isolation,
which is an operator's decision. The explicit command still makes it: the same
findings appear as **notices** in `clawk gateway migrate --multiplex --dry-run`
so you can read them first, and `--multiplex` proceeds when you confirm.

### Opting out of the automatic migration

Set `gateway.auto_multiplex_migration: false` on the **default** profile to keep
the automatic fold from ever running on this install:

```bash
clawk config set gateway.auto_multiplex_migration false
```

`clawk update` then leaves per-profile gateways exactly as they are, with no
output and no changes, however eligible the install looks. The setting lives in
config, so it survives updates — the decision is made once rather than
re-litigated on every release. It is read from the effective config like every
other setting, so a value pinned in the managed scope (`/etc/clawk/config.yaml`)
wins over the profile's own file. It governs the **automatic** path only:
`clawk gateway migrate --multiplex` is an explicit request and still migrates
(and is the supported way to opt back in). Absent or `true` keeps the default
behaviour described above.

The same setting covers a gateway that booted with only the default profile.
Normally, once you create a second profile (Desktop's New Agent or
`clawk profile create`), that gateway starts serving every profile in place,
with no restart. With `auto_multiplex_migration: false` it keeps serving only
its own profile, and the new profile is refused with that reason until you run
`clawk gateway migrate --multiplex` or set the key back to `true`. The key is
re-read on every profile rescan, so setting it back takes effect within about
30 seconds, with no restart.

The explicit command is different: `clawk gateway migrate --multiplex` with
two or more profiles and **no** standalone secondary gateway still applies the
one remaining step — it sets `gateway.multiplex_profiles: true` and (re)starts
the default gateway. You asked for multiplex; you get multiplex.

:::tip Clones do not carry channels
`clawk profile create --clone` leaves the source's bot tokens and allowlists
behind (see [Profiles → messaging channels are never cloned](./profiles.md#messaging-channels-are-never-cloned---clone-channels-to-opt-in)),
so a fleet of clones no longer trips the duplicate-credential blocker below.
Older clones that still carry them are flagged by `clawk profile list`.
:::

### What the migration does

1. Stops each secondary profile's standalone gateway and uninstalls its
   service (systemd user/system unit or launchd agent). What was removed is
   recorded in `~/.clawksis/gateway_migration.json` for rollback.
2. Sets `gateway.multiplex_profiles: true` in the **default** profile's
   `config.yaml`.
3. Restarts the default gateway — or installs and starts it on the same service
   manager the secondaries were using, so a systemd-managed fleet stays
   systemd-managed.
4. Waits for the default gateway to record `served_profiles` covering every
   profile, then prints a summary.

### Blockers and fixes

| Blocker | Why | Fix |
|---|---|---|
| Two profiles configure the same platform credential (e.g. the same `TELEGRAM_BOT_TOKEN`) | Under one process a bot token can only be polled once; the multiplexer would park the duplicate and that profile's bot would go silent | Remove the token from the second profile, or keep it in `default` and route that profile's chats with [`profile_routes`](#routing-shared-bot-chats-to-profiles-profile_routes) |
| A secondary profile enables a port-binding platform that has **no** `/p/<profile>/` ingress on the default listener | The multiplexer skips that whole profile (see [rule 2](#2-http-inbound-platforms-are-reached-via-a-pprofile-url-prefix)) | Disable the platform in that profile (`platforms.<name>.enabled: false`), or run the profile standalone: set `gateway.standalone: true` in its own `config.yaml` and wait for the host to rescan (at most 30 seconds), or send its `rescan-profiles` control verb. Use `clawk -p <name> gateway install --force` only where a boundary blocks the fold. |

The credential check reuses the gateway's own conflict detection, so its verdict
matches what the multiplexer does at startup. Which port-binding platforms have
a `/p/<profile>/` ingress is read from the adapters themselves (each declares
`serves_profile_prefix`), so the preflight stays correct as new HTTP-inbound
adapters gain the prefix.

### What changes for inbound-port profiles

A secondary profile that used `api_server` or `webhook` on its own port is
**not** blocked — but its URL changes. The preflight prints the exact new URL,
for example:

```
Profile 'coder': api_server moves onto the default listener at
http://127.0.0.1:8642/p/coder/v1/... (its key/secret is unchanged; update
clients that call the old per-profile port).
```

The profile's own `API_SERVER_KEY` / webhook secret keeps authenticating the
prefixed URL; nothing else about the key changes.

### Profiles created after the migration

A profile created while the multiplexer runs is served without a restart (see
above). `clawk profile create` confirms this when the live multiplexer picked the
profile up; it prints the `clawk gateway restart` reminder only when it could not
reach the multiplexer (for example, a gateway started from an older build).

### Failure handling and resuming

The migration is transactional. Failures it can see
coming from the plan (a system unit that would have to run as root without a
recorded `User=`, a config file it cannot rewrite) are refused before any
per-profile gateway is stopped. Anything that fails after the manifest is
written — the flag write, a later secondary's stop or unit removal, the
default's install or start — rolls back through the manifest on the spot, so no
profile is left without a gateway. Should the process die anywhere in that
window, the next `clawk gateway migrate --multiplex` sees the flag on, the
manifest, and no live multiplexer serving the migrated profiles (an installed
but stopped default unit does not count) and resumes from the manifest instead
of reporting "already multiplexed". A manifest on disk always means
*unfinished*: it is the resume record, not a rollback command — there is no
`--standalone` reverse, and the compensator above only ever runs inside a
single failed apply so that no profile is left without a gateway.

Not covered automatically: s6-supervised containers — they converge on the next
container start (the per-profile slots are registered down and the root gateway
multiplexes; a `gateway.standalone: true` profile boots its own slot from its own
run intent instead). Windows Scheduled Tasks are folded by the command. The dashboard's
System page offers the same migration as a button when the preflight finds an
eligible install.

## Updating the code

`clawk update` pulls the latest code once and syncs new bundled skills into
every profile:

```bash
clawk update
clawk-gateways restart
```

Running gateways are restarted by the update itself; on an install that still
runs one gateway per profile, the update then runs the
[migration to a single multiplexed gateway](#migrating-from-per-profile-gateways)
— automatically when nothing blocks it, otherwise as a warning naming the
boundary (different UNIX user, `CLAWK_HOME` outside `profiles/`) and the
one-liner to run yourself.

User-modified skills are never overwritten.

## Troubleshooting

### "Could not find service in domain for user gui: 501"

You ran `clawk gateway start` after a previous `clawk gateway stop`. The
CLI's `stop` does a full `launchctl unload`, which removes the service from
launchd's registry. The CLI catches this specific error on `start` and
automatically re-loads the plist (`↻ launchd job was unloaded; reloading
service definition`). The service starts normally. Nothing to fix.

### Stale PID after a crash

If a profile's gateway shows `not running` but a process is still alive:

```bash
ps -ef | grep "clawk_cli.*-p <profile>"
cat ~/.clawksis/profiles/<profile>/gateway.pid
kill -TERM <pid>          # graceful
kill -KILL <pid>          # if that fails after a few seconds
<profile> gateway start
```

### Forcing a hard reset of one service

```bash
# macOS
launchctl unload ~/Library/LaunchAgents/ai.clawk.gateway-<profile>.plist
launchctl load   ~/Library/LaunchAgents/ai.clawk.gateway-<profile>.plist

# Linux
systemctl --user restart clawk-gateway-<profile>.service
```

### Health check

```bash
clawk doctor                  # default profile
clawk -p <profile> doctor     # one profile
```
