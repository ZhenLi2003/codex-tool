# codex-tool 1.6.0 — Usage Guide

A lightweight version manager for the OpenAI Codex CLI standalone Linux x86_64 package.

## Key behavior

- Installs the complete `codex-package-x86_64-unknown-linux-musl.tar.gz`, including modern runtime companions such as `codex-code-mode-host`.
- Keeps Codex versions under `~/scripts/codex-tool/versions/` and user data under `~/.codex` untouched during install/update/switch.
- `list` is local-only and never queries GitHub.
- Large release downloads use persistent `.part` files, unlimited total transfer time by default, retry/resume, and SHA-256 verification.
- Small checksum downloads use script-level retries and do not require curl `--retry-all-errors`, improving compatibility with curl versions older than 7.71.0.
- GitHub API calls use `GITHUB_TOKEN` when set, otherwise a token saved by codex-tool. If an anonymous request receives a rate-limit `403`, codex-tool first retries that API request once with proxy use disabled. If direct access also fails and the shell is interactive, it guides the user through creating, verifying, and securely saving a GitHub access token. Release asset downloads continue to use the user's normal network/proxy settings.

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
codex-tool auth login
codex-tool auth status
codex-tool auth logout
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

If both the normal path and the direct retry fail, an interactive shell is offered an authenticated fallback. The token creation page is:

```text
https://github.com/settings/personal-access-tokens/new
```

For public `openai/codex` release metadata, codex-tool does not need repository write access. GitHub recommends fine-grained personal access tokens; the release endpoints need only `Contents: read`. The URL shown by codex-tool pre-fills that permission and a 90-day expiration.

The token is entered with terminal echo disabled, verified before saving, then stored at:

```text
~/.config/codex-tool/github-token
```

with file mode `0600`. `GITHUB_TOKEN` takes precedence when present.

The tool never changes persistent proxy environment variables.

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


## Older curl compatibility

`codex-tool` does not require the curl `--retry-all-errors` option. This option was added in curl 7.71.0 and is absent from some older enterprise Linux distributions.

Checksum-manifest downloads are retried by the shell wrapper instead, so older curl builds can still install Codex without upgrading the system curl package.

To inspect the installed curl version:

```bash
curl --version
```
