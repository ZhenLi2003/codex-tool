# codex-tool 2.1.0 — Usage Guide

Standalone Codex CLI version management for Linux x86_64, without root or npm.

## Install the manager

```bash
git clone https://github.com/ZhenLi2003/codex-tool.git
cd codex-tool
./install.sh
codex-tool version
```

The installer copies these files to `~/scripts/codex-tool/`:

```text
codex-tool
background.py
codex-launcher
```

It preserves installed versions, caches, and user configuration. It only performs narrowly scoped legacy-lock recovery when an older managed daemon has inherited a manager flock. If Optimized mode is already active, it will not restart the stopped daemon after recovery.

## Commands

```text
codex-tool install X.Y.Z [--native]
codex-tool update [--native]
codex-tool switch X.Y.Z [--native]
codex-tool delete X.Y.Z
codex-tool list

codex-tool background status
codex-tool background optimize
codex-tool background native

codex-tool clean [--all] [--dry-run] [--yes]
codex-tool prune [--dry-run] [--purge-history] [--yes] [--force]

codex-tool auth login
codex-tool auth status
codex-tool auth logout
codex-tool version
codex-tool help
```

Old `codex-tool stop` and `codex-tool daemon ...` commands are no longer public. Advanced lifecycle commands are provided by the official `codex app-server daemon ...` CLI, which codex-tool uses internally.

## Default activation policy

`install`, `update`, and `switch` default to Optimized. `--native` selects Native directly.

If a managed daemon, updater, or stale runtime record exists, the default optimization prompts:

```text
warning: Codex managed background runtime is present ...
Optimize background runtime and continue? [y/N]
```

- `y`: stop managed services (this may interrupt disconnected work), apply Optimized, activate the requested version.
- `n`: do not optimize; continue activation in Native mode.
- Noninteractive shell with a detected background runtime: fail closed unless `--native` was explicitly given.

Downloads, SHA verification, archive safety checks, and isolated CLI binary validation happen before the activation transaction. Regular manager locks use a bounded `flock` under the user-owned local runtime directory. A real concurrent manager mutation is never killed or bypassed.

## Manual installation from another device

No extra flag is needed. When a Codex package must be downloaded, `install X.Y.Z` and `update` first print:

```text
Codex release:       rust-vX.Y.Z
Official download:   https://github.com/openai/codex/releases/download/rust-vX.Y.Z/codex-package-x86_64-unknown-linux-musl.tar.gz
Manual upload path:  /absolute/path/to/scripts/codex-tool/downloads/rust-vX.Y.Z/codex-package-x86_64-unknown-linux-musl.tar.gz
Expected SHA-256:    <digest returned by official GitHub release metadata>
```

Upload the **complete standalone package archive** under that exact filename and path. The `.tar.gz.part` suffix is reserved for resumable curl downloads; never rename an incomplete upload to `.tar.gz`. For safe transfers, upload as `.tar.gz.uploading` and rename to `.tar.gz` on the server after completion.

Then rerun `codex-tool install X.Y.Z`. `update` also checks the local complete archive for the latest stable version, but latest can change between runs; `install X.Y.Z` pins the target release.

Selection order:

1. Existing complete `.tar.gz` — must be a user-owned, non-symlink regular file and have the exact official SHA-256.
2. Otherwise, existing `.tar.gz.part` — use the current resumable downloader.
3. Otherwise, download the package normally with curl.

The official release asset SHA-256 is cross-checked with the `codex-package_SHA256SUMS` manifest. All archives (manual and automatic) receive the same tar traversal/special file safety checks, full runtime-package layout checks, isolated executable version check, and daemon-safe activation.

A corrupt manual archive is preserved and rejected, **without** automatic fallback. A corrupt network partial download is removed. The version-specific cache is cleaned only after successful installation. Release metadata and the checksum manifest must still be retrieved from GitHub; manual upload is a workaround for slow large transfers, not a complete offline mode.

You can use `Ctrl+C` to stop a slow large transfer, upload the complete archive, and rerun the command. No watcher or new persistent background process is needed.

## Background policy

```bash
codex-tool background status
codex-tool background optimize
codex-tool background native
```

Optimized manages exactly four entries:

| File | Setting | Optimized |
|---|---|---|
| `CODEX_HOME/config.toml` | `check_for_update_on_startup` | `false` |
| `CODEX_HOME/config.toml` | `features.daemon_auto_start` | `false` |
| `CODEX_HOME/app-server-daemon/settings.json` | `remoteControlEnabled` | `false` |
| `CODEX_HOME/app-server-daemon/settings.json` | `updater.autoUpdateEnabled` | `false` |

Other entries, including authentication, models, MCP servers, and skills, remain untouched.

### Optimized launcher

`~/.local/bin/codex` points to `~/scripts/codex-tool/codex-launcher`.

- Ordinary interactive `codex [options]` uses `codex --no-daemon [options]`.
- `codex resume` and `codex fork` receive `--no-daemon`.
- `codex exec`, `codex agents`, `codex app-server`, other explicit service management, and noninteractive subcommands go to the original binary without injected flags.
- This is not a global guarantee that every manually requested MCP, subprocess, or agent task will disappear when the terminal closes.

The complete Codex package is still stored under `versions/X.Y.Z/`. The launcher reads `current`, so version switching does not require modifying the wrapper's source.

### Native restoration

Native mode restores the original value or absence of managed fields, then points the `codex` symlink at the native selected binary. It does not automatically start the daemon.

On first optimization, the manager saves original files and field metadata:

```text
${CODEX_TOOL_CONFIG_DIR:-~/.config/codex-tool}/background/
  manifest.json
  backup/config.toml
  backup/daemon-settings.json
```

Private backup permissions are 0700 on directories and 0600 on files. Restoration is field-specific and leaves unrelated user edits intact. If another application changes a managed value during optimization, restoration fails instead of overwriting it without warning. Complex inline TOML feature tables are rejected conservatively rather than incorrectly rewritten.

Run `codex-tool background native` to revert before manually editing managed fields, or resolve a reported conflict explicitly.

## Clean: persisted session cleanup

```bash
codex-tool clean --dry-run
codex-tool clean
codex-tool clean --all
```

Default clean captures active thread IDs before stopping a managed server and removes only sessions that were inactive before shutdown. `--all` also deletes previously active and background thread history. Both use official Codex thread RPC, not direct SQLite or rollout removal.

If Optimized is active, cleanup does not restore a long-running managed daemon. Native mode preserves the previous daemon running/stopped status where feasible. A dry-run does not stop services.

## Prune: uninstall Codex program/runtime

```bash
codex-tool prune --dry-run
codex-tool prune
codex-tool prune --purge-history
```

Prune terminates verified managed runtime services, removes the Codex CLI versions/current selection/download caches, `~/.local/bin/codex`, and managed daemon package/control directories. By default inactive saved history remains; `--purge-history` deletes all persisted threads via the official API before program removal.

Prune also restores codex-tool-managed background configuration fields before uninstalling the Codex program, so the user's Codex configuration is not left with hidden manager overrides.

Do not prune while foreground Codex processes still reference installed versions.

## GitHub API authentication

```bash
codex-tool auth login
codex-tool auth status
codex-tool auth logout
```

Saved token: `${CODEX_TOOL_CONFIG_DIR:-~/.config/codex-tool}/github-token`, mode 0600. `GITHUB_TOKEN` overrides the saved token. Public release lookup only needs GitHub read access.

If anonymous proxy access exhausts GitHub API rate limits, the manager tries direct API access once and then offers authenticated retry in an interactive TTY. Release assets use the usual configured network path.

## Runtime settings

```text
CODEX_TOOL_HISTORY_KEEP=2
CODEX_TOOL_LOCK_TIMEOUT=10
CODEX_TOOL_DOWNLOAD_RETRIES=8
CODEX_TOOL_DOWNLOAD_RETRY_DELAY=5
CODEX_TOOL_DOWNLOAD_STALL_TIME=180
CODEX_TOOL_DOWNLOAD_MAX_TIME=0
CODEX_TOOL_API_TIMEOUT=120
CODEX_TOOL_CONNECT_TIMEOUT=30
CODEX_TOOL_HOME=~/scripts/codex-tool
CODEX_TOOL_BIN_DIR=~/.local/bin
CODEX_TOOL_CONFIG_DIR=~/.config/codex-tool
CODEX_HOME=~/.codex
```

The large package downloader maintains resumable `.part` files and verifies SHA-256 using GitHub release metadata and official checksums. Small requests use Bash retries compatible with older curl versions.

## Troubleshooting

- `codex-tool background status`: inspect policy values and currently detected managed processes.
- `codex --no-daemon`: force embedded mode for one invocation.
- `codex app-server daemon version`: official managed service status.
- `codex app-server daemon stop`: official manual stop, if needed.
- If a genuine other manager mutation holds the lock, wait for it to complete; do not remove `manager.lock` to force entry.
- If a legacy managed daemon inherited a lock, the installer/manager attempts recovery only for verifiable managed process holders.
- User config conflicts under Native restoration are intentionally reported; the original backups are preserved until recovery succeeds.
