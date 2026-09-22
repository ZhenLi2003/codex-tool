# Changelog

This file summarizes the major iterations of `codex-tool`.

## 1.5.1

- Removed the hard dependency on curl `--retry-all-errors`.
- Added shell-level retries for small checksum-manifest downloads.
- Restored compatibility with older curl builds, including versions before 7.71.0 commonly found on older enterprise Linux systems.
- Kept retry behavior and SHA-256 verification unchanged from the user's perspective.

## 1.5.0

- Added GitHub API rate-limit diagnostics.
- When a GitHub REST API request returns an explicit rate-limit `403`, retry that metadata request once with proxy use disabled.
- Kept release asset downloads on the user's normal network/proxy path.
- Added clearer reporting for rate-limit reset time and direct-retry failures.
- Non-rate-limit `403` responses do not trigger proxy bypass.

## 1.4.0

- Reworked large release downloads for slow and unstable networks.
- Added persistent `.part` files under `~/scripts/codex-tool/downloads/`.
- Added resume support across retries, SSH disconnects, and later invocations.
- Removed the default whole-transfer timeout for large package downloads.
- Added configurable retry delay, retry count, stall detection, and optional per-attempt max time.
- Kept SHA-256 verification mandatory after resumed downloads.
- `prune` now also clears the persistent download cache.

## 1.3.0

- Migrated installation from the historical single `codex` executable to the complete `codex-package-x86_64-unknown-linux-musl.tar.gz` package.
- Added required runtime companions such as `codex-code-mode-host` and package resources.
- Updated the managed `codex` link to point to `current/bin/codex`.
- Added detection of legacy single-binary and incomplete installations.
- Reinstalling an affected version repairs it into the complete package layout.
- Added package-layout and archive-safety validation before activation.

## 1.2.0

- Added `prune` for removing all managed Codex versions, the active link, download state, and the managed `~/.local/bin/codex` command.
- Kept `codex-tool` itself and `~/.codex` user data intact.
- Added `--force` protection for the exceptional case where `~/.local/bin/codex` is an unrelated regular file.
- Improved handling of broken managed links after home-directory migration.

## 1.1.0

- Changed `list` to be fully local-only; it no longer queries GitHub.
- Isolated the installation-time `codex --version` validation from the real user HOME, `CODEX_HOME`, and XDG directories.
- Added overwrite-friendly manager installation while preserving installed versions, current selection, and user data.
- Improved offline behavior and regression coverage.

## 1.0.0

- Initial lightweight, non-root Codex CLI version manager for Linux x86_64.
- Added stable-version `install`, latest-stable `update`, `delete`, `switch`, `list`, and `clean` commands.
- Added strict stable-version validation.
- Added GitHub release metadata and SHA-256 validation.
- Added automatic history retention with two historical versions retained by default.
- Kept Codex user configuration/data separate under `~/.codex`.
