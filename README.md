# codex-tool

`codex-tool` is a lightweight, non-root version manager for the OpenAI Codex CLI standalone package on **Linux x86_64**.

It installs complete Codex release packages, keeps multiple versions side by side, preserves user data under `~/.codex`, supports fast version switching, and adds resilience for large GitHub downloads and GitHub API rate-limit failures.

> This is a community utility and is not an official OpenAI project.

## Why codex-tool

Codex standalone releases have evolved from a single executable into a package containing the main CLI and companion runtime components such as `codex-code-mode-host`. Installing only the `codex` binary can therefore produce incomplete installations.

`codex-tool` manages the complete Linux x86_64 package and keeps each installed version isolated under your home directory, without requiring root privileges.

Key capabilities:

- Install a specific stable Codex CLI version.
- Update to the latest stable release.
- Keep multiple versions and switch between them instantly.
- Install the complete `codex-package-x86_64-unknown-linux-musl.tar.gz` runtime.
- Preserve `~/.codex` across install, update, switch, and manager upgrades.
- Resume interrupted large downloads using persistent `.part` files.
- Verify release artifacts with SHA-256 before installation.
- Keep `list` fully local and offline.
- Detect GitHub API rate-limit `403` responses and retry that metadata request once without proxy use, while leaving large asset downloads on the user's normal network path.
- Remove all managed Codex versions with `prune` when a clean reinstall is required.

## Quick Start

Requirements:

- Linux x86_64 / amd64
- Bash
- `curl`
- `python3`
- `tar`
- `sha256sum`
- `flock`

Clone and install the manager:

```bash
git clone https://github.com/ZhenLi2003/codex-tool.git
cd codex-tool
bash install.sh

export PATH="$HOME/.local/bin:$PATH"
codex-tool version
```

Install the latest stable Codex CLI:

```bash
codex-tool update
```

Or install a specific stable version:

```bash
codex-tool install 0.154.0
```

Check locally installed versions:

```bash
codex-tool list
```

Switch versions:

```bash
codex-tool switch 0.154.0
```

## Commands

```text
codex-tool install X.Y.Z          Install/repair and activate a stable version
codex-tool update                 Install/activate the latest stable version
codex-tool delete X.Y.Z           Delete an installed non-current version
codex-tool clean [--yes]          Clear Codex data except config.toml and auth.json
codex-tool prune [--yes] [--force]
                                  Remove all managed Codex versions/download cache
                                  and the managed codex command link
codex-tool list                   Show current and locally installed versions only
codex-tool switch X.Y.Z           Activate an already installed version
codex-tool version                Show codex-tool version
codex-tool help
```

## Installation Layout

By default:

```text
~/scripts/codex-tool/
├── codex-tool
├── current -> versions/X.Y.Z
├── downloads/
└── versions/
    └── X.Y.Z/
        ├── bin/
        │   ├── codex
        │   └── codex-code-mode-host
        ├── codex-path/
        ├── codex-resources/
        └── ...

~/.local/bin/codex-tool -> ~/scripts/codex-tool/codex-tool
~/.local/bin/codex      -> ~/scripts/codex-tool/current/bin/codex
```

Codex user data remains separate:

```text
~/.codex/
```

`install`, `update`, `switch`, `delete`, and manager upgrades do not clear this directory.

## Network Resilience

Large Codex packages can exceed 100 MB. `codex-tool` stores incomplete downloads under:

```text
~/scripts/codex-tool/downloads/rust-vX.Y.Z/*.part
```

If a download is interrupted, a later retry or a later invocation can resume from the saved partial file instead of restarting from byte zero.

For GitHub REST API metadata requests, the tool normally honors the user's existing proxy configuration. If GitHub explicitly returns an API rate-limit `403`, the tool warns the user and retries that API request once with proxy use disabled. It does **not** modify proxy environment variables, and release asset downloads continue to use the user's normal network configuration.

## Configuration

Useful environment variables:

```text
GITHUB_TOKEN                      Optional GitHub token for higher API rate limits
CODEX_TOOL_HISTORY_KEEP=N         Historical versions retained (default: 2)
CODEX_TOOL_HOME=PATH              Manager directory (default: ~/scripts/codex-tool)
CODEX_TOOL_BIN_DIR=PATH           Command-link directory (default: ~/.local/bin)
CODEX_HOME=PATH                   Codex data directory (default: ~/.codex)
CODEX_TOOL_API_TIMEOUT=N          GitHub API max time in seconds (default: 120)
CODEX_TOOL_CONNECT_TIMEOUT=N      Connection timeout in seconds (default: 30)
CODEX_TOOL_DOWNLOAD_RETRIES=N     Retries after first large download attempt (default: 8)
CODEX_TOOL_DOWNLOAD_RETRY_DELAY=N Delay between large download attempts (default: 5)
CODEX_TOOL_DOWNLOAD_STALL_TIME=N  Low-speed stall threshold (default: 180)
CODEX_TOOL_DOWNLOAD_MAX_TIME=N    Per-attempt max time (default: 0 = unlimited)
```

## Documentation

- [Full usage guide](docs/USAGE.md)
- [Release history](CHANGELOG.md)
- [MIT License](LICENSE)

## Safety Notes

- Stable versions must use the strict `X.Y.Z` form.
- Release artifacts are checksum-verified before installation.
- `clean` preserves `~/.codex/config.toml` and `~/.codex/auth.json`.
- `prune` removes managed Codex installations and download cache, but preserves `codex-tool` itself and `~/.codex`.
- The manager refuses to overwrite unrelated command paths unless `--force` is explicitly requested where supported.

## License

MIT. See [LICENSE](LICENSE).
