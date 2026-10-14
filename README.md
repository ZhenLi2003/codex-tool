# codex-tool

[简体中文](docs/README.zh-CN.md)

A lightweight, non-root version manager for the **OpenAI Codex CLI standalone Linux x86_64 package**.

- Install the complete official release package without npm, Node.js, root, or sudo.
- Keep multiple CLI versions, switch versions, and retain up to two historical versions by default.
- **Optimized foreground mode by default** when installing, updating, or switching Codex.
- Use `--native` to restore Codex's original background configuration and unwrapped CLI.
- Preserve login, MCP settings, skills, sessions, and other user-owned data.
- Resume and verify large downloads, handle GitHub API rate limits, and use an optional GitHub token.
- Manage Codex sessions using official app-server APIs instead of directly deleting databases.

> Community tool; not an official OpenAI product.

## Install

```bash
git clone https://github.com/ZhenLi2003/codex-tool.git
cd codex-tool
./install.sh
export PATH="$HOME/.local/bin:$PATH"
codex-tool version
```

The installer copies `codex-tool`, `background.py`, and `codex-launcher` into `~/scripts/codex-tool/`. It does **not** change Codex's user configuration merely because the manager was installed. Background optimization is applied when a Codex version is activated.

## Version management

```bash
codex-tool update                   # latest stable Codex; optimized by default
codex-tool update --native          # latest stable Codex; original background behavior
codex-tool install 0.162.1          # install and optimize
codex-tool install 0.162.1 --native
codex-tool switch 0.162.1           # switch and optimize
codex-tool switch 0.162.1 --native
codex-tool list
codex-tool delete 0.161.0
```

Before applying optimization, if codex-tool detects an existing managed app-server or updater, it asks:

```text
Optimize background runtime and continue? [y/N]
```

- `y`: stop the verified managed runtime, apply optimized settings, and activate the version.
- `n`: continue activation in native mode, without applying optimization.
- `--native`: choose native mode directly, skipping the optimization prompt.

Stopping managed background work can interrupt active/disconnected tasks; inspect and finish them first. A genuine concurrent codex-tool operation retains its manager lock; the tool does not steal it.

## Background modes

```bash
codex-tool background status
codex-tool background optimize
codex-tool background native
```

**Optimized** sets the following managed configuration entries to `false`:

```toml
check_for_update_on_startup = false

[features]
daemon_auto_start = false
```

And in `CODEX_HOME/app-server-daemon/settings.json`:

```json
{
  "remoteControlEnabled": false,
  "updater": { "autoUpdateEnabled": false }
}
```

Only these fields are managed; all other keys are preserved.

Optimized mode changes the `~/.local/bin/codex` link to the installed `codex-launcher`, which adds `--no-daemon` to ordinary interactive Codex, `resume`, and `fork` calls. Explicit daemon/service management commands and other noninteractive commands are forwarded to the actual Codex binary. Therefore, ordinary TUI use does not start or reuse a shared app-server. This does not promise that unrelated MCP subprocesses or explicitly requested background work never run.

**Native** restores the original values or absence of the managed configuration keys and links `~/.local/bin/codex` directly to the selected native binary. It does not itself start a daemon.

Before the first optimization, the manager creates private backups and a manifest:

```text
~/.config/codex-tool/background/
├── manifest.json
└── backup/
    ├── config.toml
    └── daemon-settings.json
```

Use `CODEX_TOOL_CONFIG_DIR` and `CODEX_HOME` to override these defaults. Backup directories use `0700` and files `0600`. Restoring Native mode is **field-specific**, preserving other changes made since optimization; conflicting edits to managed fields cause an error instead of a silent overwrite.

## Session and runtime cleanup

```bash
codex-tool clean --dry-run
codex-tool clean               # delete inactive saved sessions
codex-tool clean --all         # also remove active/background sessions
codex-tool prune --dry-run
codex-tool prune               # uninstall managed CLI + daemon runtime
codex-tool prune --purge-history
```

`clean` uses Codex thread RPC; it does not directly remove session SQLite files. `prune` stops the managed runtime, removes managed program files, and restores background configuration overrides before uninstalling. Configuration, authentication, and user skills are preserved.

## Locking and lifecycle safety

Mutating manager commands use a bounded user-owned runtime lock under `$XDG_RUNTIME_DIR/codex-tool` or `/tmp/codex-tool-$UID`. Read-only commands do not acquire this lock. Long-running Codex subprocesses have the manager lock FD closed before exec. Old daemon-held locks are recovered only when the real holder can be validated as a managed Codex process; other holders cause a safe refusal.

Codex's official lifecycle and thread APIs are used for daemon and session operations. The old public `codex-tool stop` and `codex-tool daemon ...` commands have been retired; use `background status/optimize/native` for normal operation and Codex's own `codex app-server daemon ...` CLI for expert diagnostics.

## GitHub authentication and network tuning

```bash
codex-tool auth login
codex-tool auth status
codex-tool auth logout
```

`GITHUB_TOKEN` takes precedence over the saved token. Large downloads use `.part` files, SHA-256 verification, and retry/resume. See [USAGE](docs/USAGE.md) for environment variables, lifecycle details, and recovery guidance.

## License

MIT. See [LICENSE](LICENSE).
