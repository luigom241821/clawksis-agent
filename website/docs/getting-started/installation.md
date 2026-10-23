---
sidebar_position: 2
title: "Installation"
description: "Install Clawksis with desktop bundles, source installers, Docker, Nix, or the Termux APT package"
---

# Installation


Get Clawksis up and running in under two minutes with the one-line installer.


## Quick Install


### Desktop App (macOS + Windows)


Prefer a native installer?


- **Desktop downloads:** [GitHub Releases](https://github.com/samuelgradientai-sys/clawksis-agent/releases/latest)


Desktop builds ship signed/notarized macOS artifacts and Windows installers with checksum files.


### One-Line CLI Installer (Linux / macOS / WSL2)


For a git-based install that tracks `main` and gives you the latest changes immediately:


```bash

curl -fsSL https://raw.githubusercontent.com/samuelgradientai-sys/clawksis-agent/main/scripts/install.sh | bash

```


### Windows (native, PowerShell)


Native Windows runs Clawksis without WSL — the CLI, gateway, TUI, and tools all work natively. (Both native and WSL2 installs coexist cleanly; see the feature note below for the one WSL2-only feature.) Found a bug? Please [file issues](https://github.com/samuelgradientai-sys/clawksis-agent/issues).


Open PowerShell and run:


```powershell

iex (irm https://raw.githubusercontent.com/samuelgradientai-sys/clawksis-agent/main/scripts/install.ps1)

```


The installer handles **everything**: `uv`, Python 3.11, Node.js 22, `ripgrep`, `ffmpeg`, **and a portable Git Bash** (PortableGit — a self-contained Git-for-Windows distribution that ships `bash.exe` and the full POSIX toolchain Clawksis uses for shell commands; on 32-bit Windows the installer falls back to MinGit, which lacks bash and disables terminal-tool / agent-browser features).  It clones the repo under `%LOCALAPPDATA%\clawk\clawksis-agent`, creates a virtualenv, and adds `clawk` to your **User PATH**.  Restart your terminal (or open a new PowerShell window) after the install so PATH picks up.


**How Git is handled:**

1. If `git` is already on your PATH, the installer uses your existing install.

2. Otherwise it downloads portable **PortableGit** (~50MB, from the official `git-for-windows` GitHub release) and unpacks it to `%LOCALAPPDATA%\clawk\git`.  No admin rights required.  Completely isolated — it won't interfere with any system Git install, broken or otherwise.  (On 32-bit Windows it falls back to MinGit because PortableGit ships only 64-bit and ARM64 assets; bash-dependent Clawksis features won't work on 32-bit hosts.)


**Why not use winget?**  Earlier designs auto-installed Git via `winget install Git.Git`, but winget fails badly when a system Git install is in a partial or broken state (exactly when users need the installer to just work).  The portable Git approach sidesteps winget, the Windows installer registry, and any existing system Git entirely.  If the Clawksis Git install itself ever breaks, `Remove-Item %LOCALAPPDATA%\clawk\git` and re-run the installer — no system impact, no uninstall drama.


The installer also sets `CLAWK_GIT_BASH_PATH` to the located `bash.exe` so Clawksis resolves it deterministically in fresh shells.


If you prefer WSL2, the Linux installer above works inside it; both native and WSL installs can coexist without conflict (native data lives under `%LOCALAPPDATA%\clawk`, WSL data lives under `~/.clawksis`).


**Desktop installer (alternative):** A thin GUI installer is also available — download Clawksis Desktop, run the `.exe`, and on first launch it calls `install.ps1` under the hood to provision Python (via `uv`), Node, PortableGit, and the rest of the dependencies. The desktop app and the PowerShell-installed CLI share the same install and data directories, so you can use either or both. See the [Windows (Native) guide](../user-guide/windows-native#desktop-installer-alternative) for details.


### Android / Termux


Clawksis now ships a Termux-aware installer path too:


```bash

curl -fsSL https://raw.githubusercontent.com/samuelgradientai-sys/clawksis-agent/main/scripts/install.sh | bash

```


The installer detects Termux automatically and switches to a tested Android flow:

- uses Termux `pkg` for system dependencies (`git`, `python`, `nodejs`, `ripgrep`, `ffmpeg`, build tools)

- creates the virtualenv with `python -m venv`

- exports `ANDROID_API_LEVEL` automatically for Android wheel builds

- prefers the broad `.[termux-all]` extra and falls back to the smaller `.[termux]` extra (and finally a base install) if the first attempt fails to compile

- skips the untested browser / WhatsApp bootstrap by default


If you want the fully explicit path, follow the dedicated [Termux guide](./termux.md).


:::note Windows Feature Parity


Everything except the browser-based dashboard chat terminal runs natively on Windows:

- **CLI (`clawk chat`, `clawk setup`, `clawk gateway`, …)** — native, uses your default terminal

- **Gateway (Telegram, Discord, Slack, …)** — native, runs as a background PowerShell process

- **Cron scheduler** — native

- **Browser tool** — native (Chromium via Node.js)

- **MCP servers** — native (stdio and HTTP transports both supported)

- **Dashboard `/chat` terminal pane** — **WSL2 only** (uses a POSIX PTY; native Windows has no equivalent).  The rest of the dashboard (sessions, jobs, metrics) works natively — only the embedded PTY terminal tab is gated.


Set `CLAWK_DISABLE_WINDOWS_UTF8=1` in your environment if you hit an encoding-related bug and want to fall back to the legacy cp1252 stdio path (useful for bisecting).
:::

### What the Installer Does

The installer handles everything automatically — all dependencies (Python, Node.js, ripgrep, ffmpeg), the repo clone, virtual environment, global `clawk` command setup, and LLM provider configuration. By the end, you're ready to chat.

#### Install Layout

Where the installer puts things depends on whether you're installing as a normal user or as root:

| Installer | Code lives at | `clawk` binary | Data directory |

|---|---|---|---|

| pip install | Python site-packages | `~/.local/bin/clawk` (console_scripts) | `~/.clawksis/` |

| Per-user (git installer) | `~/.clawksis/clawksis-agent/` | `~/.local/bin/clawk` (symlink) | `~/.clawksis/` |

| Root-mode (`sudo curl … \| sudo bash`) | `/usr/local/lib/clawksis-agent/` | `/usr/local/bin/clawk` | `/root/.clawksis/` (or `$CLAWK_HOME`) |

The root-mode **FHS layout** (`/usr/local/lib/…`, `/usr/local/bin/clawk`) matches where other system-wide developer tools land on Linux. It's useful for shared-machine deployments where one system install should serve every user. Per-user config (auth, skills, sessions) still lives under each user's `~/.clawksis/` or explicit `CLAWK_HOME`.

### After Installation

Reload your shell and start chatting:

```bash
source ~/.bashrc   # or: source ~/.zshrc
clawk             # Start chatting!
```

To reconfigure individual settings later, use the dedicated commands:

```bash
clawk model          # Choose your LLM provider and model
clawk tools          # Configure which tools are enabled
clawk gateway setup  # Set up messaging platforms
clawk config set     # Set individual config values
clawk setup          # Or run the full setup wizard to configure everything at once
```

:::tip Fastest path: Nous Portal
One subscription covers 300+ models plus the [Tool Gateway](../user-guide/features/tool-gateway.md) (web search, image generation, TTS, cloud browser). Skip the per-tool key juggling:

```bash
clawk setup --portal
```

That logs you in, sets Nous as your provider, and turns on the Tool Gateway in one command.
:::

:::tip Already running Clawksis on another machine?
You don't need to rebuild your setup from scratch. Restore a full backup with `clawk import` (see [Exporting Clawksis to another machine](../reference/faq.md#exporting-clawk-to-another-machine)), or bring over a single agent with `clawk profile import` (see [Moving a single profile to another machine](../reference/faq.md#moving-a-single-profile-to-another-machine)). Note that a profile export excludes credentials by design, so an export alone is not a full backup — [`clawk backup` vs `clawk profile export`](../reference/faq.md#clawk-backup-vs-clawk-profile-export) explains which to use.
:::

---

## Prerequisites

For the POSIX source script, provide Git, curl, tar, and SHA-256 utilities.
Windows can bootstrap its pinned Git for Windows archive when Git is absent.
The script always downloads its verified uv pin; a uv already on your PATH is never used.

Current first-party installations run on **Python 3.14**. The broader
`>=3.11,<3.15` range in `pyproject.toml` lets older Python installations
run the updater before PM switches them to 3.14; it does not promise current
runtime support on 3.11–3.13. PM selects the managed tool versions from
`pm/lock.json`; it does not adopt arbitrary system Node versions as the
installed runtime.

Source builds can require a native compiler and platform development libraries.
Building Electron from source adds Node native-module requirements. These
build prerequisites do not apply to installing a complete desktop package.
Linux Chromium also requires system libraries supplied by the distribution.

On glibc Linux, the managed Node.js links `libatomic.so.1`, which minimal
Debian, Ubuntu and RHEL-family images do not ship. When the library is
missing, the installer and `clawk update` install the distro package
(`libatomic1` on apt and zypper, `libatomic` on dnf/yum and apk, `gcc-libs`
on pacman). They run the package manager directly as root, or as
`sudo -n` otherwise. An interactive run asks for your sudo password once,
before installing dependencies. `--non-interactive` runs never prompt. If
the install cannot run, the error names the exact command for the package
manager it found.

:::tip Nix users

If you use Nix (on NixOS, macOS, or Linux), there's a dedicated setup path with a Nix flake, declarative NixOS module, and optional container mode. See the **[Nix & NixOS Setup](./nix-setup.md)** guide.
:::

---

## Manual / Developer Installation

For a source checkout, start with the
[PM developer workflow](../reference/package-management.md#developer-workflow).
It covers activation, daily commands, dependency refresh, and current bootstrap limits.
[Development Setup](../developer-guide/contributing.md#development-setup) covers the separate test environment and checks.

---

## Non-Sudo / System Service User Installs

Run the source installer as the intended service user. Its home, tool store,
configuration, and launcher must belong to that user.

1. As an administrator, install the source-build prerequisites and any Linux
   libraries needed by the selected browser backend.
2. As the service user, run the regular installer:

   ```bash

   curl -fsSL https://raw.githubusercontent.com/samuelgradientai-sys/clawksis-agent/main/scripts/install.sh | bash
   ```

3. Add the actual launcher directory to the service user's shell environment:

   ```bash
   export PATH="$HOME/.local/bin:$PATH"
   ```

4. Run `clawk doctor` from that account. Use the installed wrapper, not a
   hardcoded `venv/bin/clawk` path.
5. For a Linux user service that must survive logout, enable lingering as an administrator:

   ```bash
   sudo loginctl enable-linger SERVICE_USER
   ```

The current source installer does not run Playwright's `--with-deps` step.
Apart from Node.js's `libatomic` (see Prerequisites), it does not install
system packages. PM manages tool binaries; the administrator supplies system
libraries. A service user without sudo gets the exact `libatomic` command to
ask an administrator to run. See
[Browser automation](../user-guide/features/browser.md) and
[Messaging Gateway](../user-guide/messaging/index.md).

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `clawk: command not found` | Reload your shell (`source ~/.bashrc`) or check PATH |
| `API key not set` | Run `clawk model` to configure your provider, or `clawk config set OPENROUTER_API_KEY your_key` |
| Missing config after update | Run `clawk config check` then `clawk config migrate` |

For more diagnostics, run `clawk doctor` — it will tell you exactly what's missing and how to fix it.

### Symlinked home directories and external storage

Clawksis supports a symlinked `CLAWK_HOME` and symlinked home subdirectories,
including `hooks`, `skills`, `sessions`, and `logs`. During home initialization,
existing directory links are preserved, and permissions on linked directories
(and descendants such as `logs/curator`) are left to their owner.

If a link target is missing, inaccessible, or not a directory, initialization
stops with a storage error naming the path and link target. Clawksis does **not**
replace the link or create its missing target: doing so could write data onto
the local disk while an external or NAS volume is unmounted. Check the reported
link, restore the mount or correct its target, and verify access permissions
before retrying. For a deliberately new dotfiles target, create it yourself only
after confirming the intended storage is available.

`clawk doctor` reports these failures as storage problems, not invalid YAML.
Keep your existing `config.yaml`; running `clawk setup` is not the repair for an
unavailable directory. This is a directory-availability check, not a mount monitor:
an existing directory cannot establish that the intended volume is mounted.

## Install method auto-detection

The update owner depends on the running installation, not only its data home.
Source checkouts use the managed Git update path. Desktop bundles, Docker,
Nix, and Termux packages retain their package owner's update mechanism.
`clawk doctor` reports installation provenance. See
[Updating & Uninstalling](./updating.md) before changing package-owned files.
