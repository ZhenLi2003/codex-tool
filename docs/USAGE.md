# codex-tool 1.9.0 — Usage Guide

A lightweight version manager for the OpenAI Codex CLI standalone Linux x86_64 package.

## Key behavior

- Installs the complete `codex-package-x86_64-unknown-linux-musl.tar.gz`, including modern runtime companions such as `codex-code-mode-host`.
- Keeps Codex versions under `~/scripts/codex-tool/versions/` and treats modern app-server daemon state under `CODEX_HOME` as lifecycle-managed state rather than disposable cache.
- `install`, `update`, and `switch` stop/restore a healthy managed daemon only around the activation transaction.
- Read-only commands do not acquire the exclusive manager lock; mutation commands use a bounded host-local runtime lock.
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
codex-tool stop
codex-tool clean [--all] [--dry-run] [--yes]
codex-tool prune [--dry-run] [--yes] [--force]
codex-tool daemon status
codex-tool daemon stop
codex-tool daemon repair [--yes]
codex-tool list
codex-tool switch X.Y.Z
codex-tool auth login
codex-tool auth status
codex-tool auth logout
codex-tool version
```

`clean` manages persisted sessions through the Codex app-server protocol. `prune` is the program/runtime cleanup operation: it removes loaded/background thread records, stops the managed daemon, removes codex-tool-managed CLI assets plus Codex managed daemon/standalone runtime packages, and preserves inactive saved history and user configuration/authentication.

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


## Daemon-aware lifecycle

Codex app-server daemon state is not treated as disposable user cache.

### Version activation

For `install`, `update`, and `switch`:

1. download, checksum verification, archive validation, and isolated binary validation happen while the existing daemon keeps running;
2. immediately before changing the active CLI or replacing an installed version, codex-tool snapshots daemon state;
3. a healthy managed daemon is stopped through `codex app-server daemon stop`;
4. the version selection is changed atomically;
5. if the daemon was previously running, codex-tool starts it again through the official lifecycle command;
6. history pruning runs only after daemon restoration succeeds.

If restoration fails, the selected CLI remains active, the command returns failure, and older versions are retained.

An unmanaged app-server is never terminated automatically. Stale or unknown daemon state causes mutation commands to fail closed and direct the user to `codex-tool daemon repair`.

### clean / prune in 1.9.0

`CODEX_HOME` is treated as Codex-owned state. codex-tool does not directly delete rollout/session directories or SQLite databases.

Session management is performed through app-server JSON-RPC using `thread/list`, `thread/read`, `thread/loaded/list`, `thread/turns/list`, `turn/interrupt`, and `thread/delete`.

#### clean

```bash
codex-tool clean --dry-run
codex-tool clean
codex-tool clean --all
codex-tool clean --all --yes
```

Default behavior:

- enumerate both active and archived persisted threads;
- snapshot the IDs that are active before the stop boundary;
- stop the managed app-server through the official daemon lifecycle;
- delete only threads that were already inactive before the stop;
- preserve the pre-stop active/background thread records;
- restore the managed daemon when it was running before clean.

With `--all`, the same stop boundary is used but every persisted thread is deleted, including threads that were active/background before app-server was stopped.

If the online interrupt/delete pass cannot remove every thread because managed live/internal state is still holding ownership, `clean --all` establishes a final boundary by temporarily stopping the managed daemon, retries cleanup through an isolated stdio app-server, then restores the daemon. An unmanaged app-server is never stopped automatically.

#### prune

```bash
codex-tool prune --dry-run
codex-tool prune
codex-tool prune --yes
```

Prune is intentionally broader:

- refuse to continue while a foreground Codex process is executing from managed program files;
- enumerate all threads currently loaded by app-server;
- request interruption for active background turns;
- stop the managed daemon through the official lifecycle API;
- use a temporary stdio app-server to delete persisted records belonging to the previously loaded/background threads;
- remove codex-tool-managed versions/current/download cache and the managed `codex` command;
- remove `CODEX_HOME/packages/app-server-daemon`, `CODEX_HOME/packages/standalone`, `CODEX_HOME/app-server-daemon`, and `CODEX_HOME/app-server-control`.

Prune preserves inactive saved thread history as well as user configuration, authentication, skills, rules, memories, and other Codex-owned user state.

Transient/internal loaded workers that have no persisted thread record after daemon shutdown are treated as already gone rather than as deletion failures.

### daemon status

```bash
codex-tool daemon status
```

Reports lifecycle support, classified daemon state, control binary/backend, managed/running versions and socket path when available, plus managed process IDs for diagnostic use.

### daemon repair

```bash
codex-tool daemon repair
```

This is the explicit stale-state recovery path. It first tries the official daemon stop command. If that fails, it identifies only user-owned Codex app-server processes, terminates them, validates the protected `/tmp/codex-daemon-UID` directory before touching it, and removes transient PID/socket/lock state. It preserves:

```text
CODEX_HOME/app-server-daemon/settings.json
CODEX_HOME/app-server-daemon/loaded-threads.json
CODEX_HOME/app-server-daemon/*.log
CODEX_HOME/packages/
```

If stale state indicates a daemon had been active, repair attempts to start it again.

### Running-process protection

A version directory is not removed while a user-owned process still executes a binary from it. This protection applies to explicit `delete`, automatic history pruning, same-version repair/replacement, and full `prune`.


## Manager locking in 1.7.1

The manager lock is no longer taken before command dispatch.

Read-only commands:

```text
version
help
list
auth status
daemon status
```

run without the exclusive manager lock. In particular, `version` and `help` also avoid unrelated dependency checks such as curl/tar/sha256sum.

Mutation commands obtain an exclusive lock in a host-local runtime directory:

```text
$XDG_RUNTIME_DIR/codex-tool
```

when a user-owned runtime directory is available, otherwise:

```text
/tmp/codex-tool-$UID
```

The directory is validated as a real, user-owned directory and forced to mode `0700`.

Default lock wait:

```text
CODEX_TOOL_LOCK_TIMEOUT=10
```

If the lock cannot be acquired within that interval, codex-tool exits with a diagnostic instead of blocking indefinitely. When a valid holder PID file is available, the error includes the holder PID and command line.


## Lock, stop, and subprocess isolation in 1.9.0

The 1.7.1 bounded runtime lock remains in place. 1.8.0 additionally prevents lock-file descriptor inheritance.

Every Codex child invoked for daemon lifecycle or session administration closes manager FD 9 before exec. The temporary Python app-server client is also launched with FD 9 closed, and Python uses `close_fds=True` for Codex children. On codex-tool exit, the parent explicitly unlocks and closes FD 9.

This prevents a detached app-server or updater from retaining the codex-tool `flock` after the original manager process exits.


## stop in 1.9.0

```bash
codex-tool stop
codex-tool daemon stop
```

Both commands stop the managed Codex app-server. The top-level `stop` is intentionally not a normal manager mutation: it does not acquire the codex-tool manager lock first.

This makes it usable as a recovery primitive when an older daemon inherited the manager lock file descriptor. Before stopping, codex-tool inspects actual lock holders:

- a real in-flight `codex-tool` mutation causes `stop` to fail closed;
- verified managed Codex daemon holders are allowed and are stopped;
- unknown holders cause `stop` to fail closed.

The normal path uses `codex app-server daemon stop`. Stale-state fallback terminates only verified managed Codex app-server/updater processes and then cleans transient PID/socket state.

Mutation commands use the same stop primitive automatically. Before acquiring their manager lock, they also detect the legacy case where a managed daemon itself holds the lock. In that case codex-tool snapshots active and loaded thread IDs, stops the daemon, waits for the lock to become free, and then continues the requested mutation. Version activation and clean restore the daemon afterward when appropriate; prune intentionally leaves it stopped.

The installer performs equivalent legacy-lock recovery before overwriting the installed manager, so upgrading from versions affected by FD inheritance does not require manually killing the daemon.
