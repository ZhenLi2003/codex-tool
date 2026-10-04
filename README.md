# codex-tool

[简体中文](docs/README.zh-CN.md)

A lightweight version manager for the OpenAI Codex CLI standalone package on **Linux x86_64**.

`codex-tool` is designed for users who want a simple Codex CLI installation without changing the system environment:

- **No root / sudo required** — everything is installed inside your home directory.
- **No npm or Node.js required** — installs the official standalone Codex package directly from GitHub Releases.
- **Simple installation** — only two project scripts are involved: `install.sh` and `codex-tool`.
- **Version switching** — keep multiple Codex versions side by side and switch instantly.
- **Complete modern runtime** — installs the full Codex package, including components such as `codex-code-mode-host`.
- **Daemon-aware lifecycle** — version activation coordinates with the managed app-server daemon; session cleanup uses Codex's official app-server APIs instead of deleting `CODEX_HOME` internals.
- **Non-blocking read-only commands** — `version`, `help`, `list`, `auth status`, and `daemon status` do not take the exclusive manager lock.
- **User data ownership respected** — codex-tool manages its own CLI versions directly and asks Codex to manage persisted threads through app-server RPC.
- **Resilient downloads** — large release packages support persistent resume/retry and SHA-256 verification.
- **GitHub API rate-limit recovery** — if an anonymous proxy exit exhausts GitHub's API quota, codex-tool first retries the metadata request directly; if direct access is unavailable, it can guide you to create a GitHub access token, verify it, save it with mode `0600`, and reuse it for future API requests.

> `codex-tool` is a community utility and is not an official OpenAI project.

## Quick Start

### 1. Clone and install the manager

```bash
git clone https://github.com/ZhenLi2003/codex-tool.git
cd codex-tool
./install.sh
```

If `~/.local/bin` is not already in the current shell's `PATH`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Verify the manager:

```bash
codex-tool version
```

### 2. Install Codex CLI

Install the latest stable version:

```bash
codex-tool update
```

Or install a specific stable version:

```bash
codex-tool install 0.154.0
```

No `sudo`, `npm install -g`, or Node.js runtime is required.

## Version Management

List locally installed versions:

```bash
codex-tool list
```

Switch to an installed version:

```bash
codex-tool switch 0.154.0
```

Delete an old non-current version:

```bash
codex-tool delete 0.153.0
```

By default, the active version plus up to two historical versions are retained.

## Commands

```text
codex-tool install X.Y.Z          Install/repair and activate a stable version
codex-tool update                 Install/activate the latest stable version
codex-tool list                   Show current and locally installed versions
codex-tool switch X.Y.Z           Switch to an installed version
codex-tool delete X.Y.Z           Delete an installed non-current version
codex-tool clean [--all] [--dry-run] [--yes]
                                  Delete persisted sessions through the Codex app-server.
                                  Default: inactive threads only; --all also interrupts
                                  and deletes active/background threads.
codex-tool prune [--dry-run] [--yes] [--force]
                                  Delete loaded/background threads, stop the daemon,
                                  and remove Codex program/runtime assets while
                                  preserving inactive saved history and user config/auth
codex-tool version                Show codex-tool version
codex-tool daemon status          Inspect app-server daemon state
codex-tool daemon repair [--yes]  Repair stale managed daemon runtime state
codex-tool auth login             Save and verify a GitHub access token
codex-tool auth status            Show the active GitHub auth source
codex-tool auth logout            Remove the token saved by codex-tool
codex-tool help                   Show built-in help
```

## Requirements

`codex-tool` targets **Linux x86_64 / amd64** and uses common command-line utilities:

- Bash
- `curl`
- `python3`
- `tar`
- `sha256sum`
- `flock`

It does **not** require:

- root privileges
- `sudo`
- npm
- Node.js
- a system-wide Codex installation

## How It Installs

The manager itself lives under your home directory:

```text
~/scripts/codex-tool/
├── codex-tool
├── current -> versions/X.Y.Z
├── downloads/
└── versions/
    └── X.Y.Z/
        ├── bin/codex
        ├── bin/codex-code-mode-host
        ├── codex-path/
        ├── codex-resources/
        └── ...
```

Command links are created in:

```text
~/.local/bin/codex-tool
~/.local/bin/codex
```

Codex configuration and runtime data remain in:

```text
~/.codex/
```

Updating the manager or switching Codex versions does not clear that directory.

## Daemon-aware lifecycle

Modern Codex uses a long-lived app-server, persisted thread storage, SQLite-backed state, writer locks, and managed daemon packages. codex-tool 1.8.0 no longer treats `CODEX_HOME` as a cache directory.

For `install`, `update`, and `switch`, codex-tool keeps the existing daemon running during download and package verification, then stops/restores a healthy managed daemon only around version activation.

For session cleanup, codex-tool uses the official app-server JSON-RPC methods rather than deleting rollout files or SQLite databases directly:

```text
thread/list
thread/read
thread/loaded/list
thread/turns/list
turn/interrupt
thread/delete
```

### clean

```bash
codex-tool clean --dry-run
codex-tool clean
codex-tool clean --all
```

Default `clean` deletes persisted threads whose current status is not active. Healthy background app-server/daemon processes stay running.

`clean --all` additionally requests `turn/interrupt` for active threads, waits for them to leave the active state, then deletes their persisted thread records through `thread/delete`.

No clean mode directly removes `sessions/`, `archived_sessions/`, `thread_history_*.sqlite`, `state_*.sqlite`, or Codex lock files.

### prune

`prune` is the program/runtime cleanup operation. It:

1. discovers loaded/background threads through app-server;
2. requests interruption for active turns;
3. stops the managed daemon;
4. deletes persisted records for the previously loaded/background threads through a temporary stdio app-server;
5. removes codex-tool-managed CLI versions, current/download cache, the managed `codex` command, managed daemon/standalone packages, and daemon runtime state.

It preserves inactive saved thread history and user-owned configuration/authentication/skills/rules.

Foreground Codex processes using managed binaries cause prune to fail closed rather than deleting executables beneath a running process.

Diagnostics and stale-state recovery remain available:

```bash
codex-tool daemon status
codex-tool daemon repair
```

## GitHub API authentication

Anonymous GitHub REST API requests are rate-limited per source IP. This is often visible on shared laboratory or proxy egress addresses.

When an anonymous request is rate-limited, codex-tool:
1. retries that API metadata request once without proxy use;
2. if direct access fails and the shell is interactive, shows a pre-filled GitHub fine-grained token creation URL;
3. requests only read access to repository contents, accepts the token with hidden input, verifies it against the public `openai/codex` release API, and stores it at `~/.config/codex-tool/github-token` with mode `0600`.

You can manage the saved token explicitly:

```bash
codex-tool auth login
codex-tool auth status
codex-tool auth logout
```

`GITHUB_TOKEN`, when set, takes precedence over the saved token.

## Manager locking

codex-tool 1.7.1 no longer takes an exclusive lock for read-only commands such as:

```bash
codex-tool version
codex-tool help
codex-tool list
codex-tool auth status
codex-tool daemon status
```

Mutation commands use a host-local runtime lock under `$XDG_RUNTIME_DIR/codex-tool` when available, otherwise `/tmp/codex-tool-$UID`. The lock directory must be owned by the current user and is forced to mode `0700`.

Lock acquisition is bounded by `CODEX_TOOL_LOCK_TIMEOUT` (default: 10 seconds). If another mutation still holds the lock, codex-tool reports the holder PID/command when available instead of waiting indefinitely.

In 1.8.0, every Codex subprocess that can start or communicate with a long-lived daemon explicitly closes the manager-lock file descriptor before exec. The codex-tool parent also explicitly unlocks/closes it on exit. This prevents app-server or updater descendants from accidentally keeping the codex-tool `flock` alive after the manager exits.

## Documentation

- [Full usage guide](docs/USAGE.md)
- [简体中文说明](docs/README.zh-CN.md)
- [Release history](docs/CHANGELOG.md)
- [MIT License](LICENSE)

## License

MIT. See [LICENSE](LICENSE).
