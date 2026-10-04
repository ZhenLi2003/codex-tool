# codex-tool

[简体中文](docs/README.zh-CN.md)

A lightweight version manager for the OpenAI Codex CLI standalone package on **Linux x86_64**.

`codex-tool` is designed for users who want a simple Codex CLI installation without changing the system environment:

- **No root / sudo required** — everything is installed inside your home directory.
- **No npm or Node.js required** — installs the official standalone Codex package directly from GitHub Releases.
- **Simple installation** — only two project scripts are involved: `install.sh` and `codex-tool`.
- **Version switching** — keep multiple Codex versions side by side and switch instantly.
- **Complete modern runtime** — installs the full Codex package, including components such as `codex-code-mode-host`.
- **Daemon-aware lifecycle** — version activation stops/restores the managed app-server daemon safely, and `clean` no longer deletes daemon state or packages.
- **User data preserved** — `~/.codex` configuration, authentication, managed daemon packages, and unknown future state are preserved unless explicitly owned by codex-tool.
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
codex-tool clean [--yes]          Clear known history/log data only; preserve config,
                                  auth, daemon state/packages, and unknown entries
codex-tool prune [--yes] [--force]
                                  Stop managed daemon if needed, then remove all
                                  codex-tool-managed versions/cache and codex link
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

Modern Codex can run a managed background app-server under `CODEX_HOME`. codex-tool 1.7.0 treats that daemon as an independent lifecycle-managed component:

- `install`, `update`, and `switch` perform downloads/verification first, then stop a healthy managed daemon only for the activation transaction and restore it afterward.
- If daemon restoration fails, the selected CLI remains active, previous versions are retained, and codex-tool reports the failure instead of deleting recovery options.
- `prune` stops a managed daemon and intentionally leaves it stopped while preserving `CODEX_HOME/packages/app-server-daemon` and daemon settings/state.
- `clean` uses a delete allowlist. It removes only known history/log data: `sessions/`, `archived_sessions/`, `history.jsonl`, and `log/`.
- `clean` never wipes the whole `CODEX_HOME`, so `config.toml`, `auth.json`, daemon state, packages, and unknown future Codex entries are preserved.
- Running Codex processes protect their version directories from `delete`, automatic history pruning, replacement, and `prune`.

Diagnostics and stale-state recovery:

```bash
codex-tool daemon status
codex-tool daemon repair
```

The normal lifecycle commands fail closed when daemon state is stale/unknown or when an unmanaged app-server is running. `daemon repair` is the explicit recovery path for stale managed daemon runtime state.

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

## Documentation

- [Full usage guide](docs/USAGE.md)
- [简体中文说明](docs/README.zh-CN.md)
- [Release history](docs/CHANGELOG.md)
- [MIT License](LICENSE)

## License

MIT. See [LICENSE](LICENSE).
