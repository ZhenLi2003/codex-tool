# codex-tool 1.5.0 — Usage Guide

A lightweight version manager for the OpenAI Codex CLI standalone Linux x86_64 package.

## Key behavior

- Installs the complete `codex-package-x86_64-unknown-linux-musl.tar.gz`, including modern runtime companions such as `codex-code-mode-host`.
- Keeps Codex versions under `~/scripts/codex-tool/versions/` and user data under `~/.codex` untouched during install/update/switch.
- `list` is local-only and never queries GitHub.
- Large release downloads use persistent `.part` files, unlimited total transfer time by default, retry/resume, and SHA-256 verification.
- GitHub API calls normally honor the user's existing proxy configuration. If GitHub returns a rate-limit `403`, codex-tool explains the condition and retries that API request once with proxy use disabled (`--proxy '' --noproxy '*'`). This fallback is limited to GitHub API metadata requests; release asset downloads continue to use the user's normal network/proxy settings.

## Install / overwrite manager

```bash
./install.sh
```

Use `./install.sh --force` only if `~/.local/bin/codex-tool` is occupied by an unrelated path that you intentionally want to replace.

The installer overwrites the manager script but preserves `versions/`, `current`, `downloads/`, and `~/.codex`.

## Commands

```text
codex-tool install X.Y.Z
codex-tool update
codex-tool delete X.Y.Z
codex-tool clean [--yes]
codex-tool prune [--yes] [--force]
codex-tool list
codex-tool switch X.Y.Z
codex-tool version
```

`prune` removes all managed Codex versions, the `current` link, download cache, and `~/.local/bin/codex`. It keeps `codex-tool` and `~/.codex`.

## GitHub API rate-limit fallback

Typical output when a shared proxy exit has exhausted GitHub's anonymous API quota:

```text
==> checking the latest stable GitHub release
warning: latest Codex release was rejected by GitHub API rate limiting (HTTP 403, remaining=0).
warning: GitHub: API rate limit exceeded for ...
warning: retrying this GitHub API request once with proxy use disabled; asset downloads will keep the normal proxy configuration.
warning: direct GitHub API retry succeeded; continuing without changing your proxy environment.
```

The tool does not try to detect whether a proxy exists. It reacts only to a GitHub API rate-limit response. Non-rate-limit `403` responses are reported normally and do not trigger proxy bypass.

If both the normal path and the direct retry fail, no persistent proxy environment variable is changed.

## Download tuning

Defaults:

```text
CODEX_TOOL_CONNECT_TIMEOUT=30
CODEX_TOOL_API_TIMEOUT=120
CODEX_TOOL_DOWNLOAD_RETRIES=8
CODEX_TOOL_DOWNLOAD_RETRY_DELAY=5
CODEX_TOOL_DOWNLOAD_STALL_TIME=180
CODEX_TOOL_DOWNLOAD_MAX_TIME=0
```

`CODEX_TOOL_DOWNLOAD_MAX_TIME=0` means no total-time limit for each large-file transfer attempt.
