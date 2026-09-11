# codex-tool

[简体中文](docs/README.zh-CN.md)

A lightweight version manager for the OpenAI Codex CLI standalone package on **Linux x86_64**.

`codex-tool` is designed for users who want a simple Codex CLI installation without changing the system environment:

- **No root / sudo required** — everything is installed inside your home directory.
- **No npm or Node.js required** — installs the official standalone Codex package directly from GitHub Releases.
- **Simple installation** — only two project scripts are involved: `install.sh` and `codex-tool`.
- **Version switching** — keep multiple Codex versions side by side and switch instantly.
- **Complete modern runtime** — installs the full Codex package, including components such as `codex-code-mode-host`.
- **User data preserved** — `~/.codex` is kept separate from managed program versions.
- **Resilient downloads** — large release packages support persistent resume/retry and SHA-256 verification.
- **GitHub API rate-limit fallback** — when GitHub explicitly reports API quota exhaustion, the metadata request is retried once without proxy use while normal asset downloads keep the user's network configuration.

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
codex-tool clean [--yes]          Clear Codex data except config.toml and auth.json
codex-tool prune [--yes] [--force]
                                  Remove all managed Codex versions/download cache
                                  and the managed codex command link
codex-tool version                Show codex-tool version
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

## Documentation

- [Full usage guide](docs/USAGE.md)
- [简体中文说明](docs/README.zh-CN.md)
- [Release history](docs/CHANGELOG.md)
- [MIT License](LICENSE)

## License

MIT. See [LICENSE](LICENSE).
