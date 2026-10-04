#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

TOOL_HOME="\${CODEX_TOOL_HOME:-$HOME/scripts/codex-tool}"
BIN_DIR="\${CODEX_TOOL_BIN_DIR:-$HOME/.local/bin}"
CODEX_DATA_DIR="\${CODEX_HOME:-$HOME/.codex}"
FORCE=0
RESTART_DAEMON_AFTER_INSTALL=0

[[ "\${1:-}" != "--force" ]] || { FORCE=1; shift; }
[[ $# -eq 0 ]] || { echo "usage: ./install.sh [--force]" >&2; exit 2; }

log()  { printf '==> %s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

SRC_DIR="$(cd "$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
[[ -x "$SRC_DIR/codex-tool" ]] || die "codex-tool payload is missing"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

manager_lock_files() {
  local runtime_owner=""
  if [[ -n "\${XDG_RUNTIME_DIR:-}" && -d "$XDG_RUNTIME_DIR" && ! -L "$XDG_RUNTIME_DIR" ]]; then
    runtime_owner="$(stat -c '%u' "$XDG_RUNTIME_DIR" 2>/dev/null || true)"
    if [[ "$runtime_owner" == "$UID" ]]; then
      printf '%s\n' "$XDG_RUNTIME_DIR/codex-tool/manager.lock"
    fi
  fi
  printf '%s\n' "/tmp/codex-tool-$UID/manager.lock"
  # 1.7.0 used a lock under TOOL_HOME. It no longer blocks new releases, but
  # recovering it here also prevents an old daemon from retaining that inode.
  printf '%s\n' "$TOOL_HOME/.lock"
}

lock_is_free() {
  local lock_file="$1"
  [[ -e "$lock_file" || -L "$lock_file" ]] || return 0
  [[ -f "$lock_file" && ! -L "$lock_file" ]] || return 1

  local rc=1
  exec 8>>"$lock_file"
  if flock -n -x 8; then
    flock -u 8 2>/dev/null || true
    rc=0
  fi
  exec 8>&-
  return "$rc"
}

lock_holder_pids() {
  local lock_file="$1"
  [[ -f "$lock_file" && ! -L "$lock_file" ]] || return 0

  local key=""
  key="$(stat -Lc '%d:%i' "$lock_file" 2>/dev/null || true)"
  [[ -n "$key" ]] || return 0

  local proc pid proc_uid fd fd_key
  for proc in /proc/[0-9]*; do
    [[ -r "$proc/status" && -d "$proc/fd" ]] || continue
    proc_uid="$(awk '/^Uid:/{print $2; exit}' "$proc/status" 2>/dev/null || true)"
    [[ "$proc_uid" == "$UID" ]] || continue
    pid="\${proc##*/}"

    for fd in "$proc"/fd/*; do
      [[ -e "$fd" || -L "$fd" ]] || continue
      fd_key="$(stat -Lc '%d:%i' "$fd" 2>/dev/null || true)"
      if [[ -n "$fd_key" && "$fd_key" == "$key" ]]; then
        printf '%s\n' "$pid"
        break
      fi
    done
  done
}

pid_cmdline() {
  local pid="$1"
  tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true
}

pid_exe() {
  local pid="$1" exe=""
  exe="$(readlink "/proc/$pid/exe" 2>/dev/null || true)"
  printf '%s\n' "\${exe% (deleted)}"
}

is_codex_tool_holder() {
  local pid="$1" cmd
  cmd="$(pid_cmdline "$pid")"
  [[ "$cmd" =~ (^|[[:space:]])([^[:space:]]*/)?codex-tool([[:space:]]|$) ]]
}

is_managed_daemon_holder() {
  local pid="$1" exe cmd
  exe="$(pid_exe "$pid")"
  cmd="$(pid_cmdline "$pid")"

  case "$exe" in
    "$TOOL_HOME/versions/"*|"$CODEX_DATA_DIR/packages/"*) ;;
    *) return 1 ;;
  esac

  [[ "$cmd" == *"app-server"* || "$cmd" == *"pid-update-loop"* || "$cmd" == *"--managed-daemon"* ]]
}

find_daemon_control_binary() {
  local candidate from_path=""
  from_path="$(command -v codex 2>/dev/null || true)"
  for candidate in \
    "$TOOL_HOME/current/bin/codex" \
    "$TOOL_HOME/current/codex" \
    "$BIN_DIR/codex" \
    "$from_path" \
    "$CODEX_DATA_DIR/packages/app-server-daemon/current/bin/codex" \
    "$CODEX_DATA_DIR/packages/standalone/current/bin/codex"
  do
    [[ -n "$candidate" && -x "$candidate" ]] || continue
    if "$candidate" app-server daemon --help >/dev/null 2>&1; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

daemon_reports_running() {
  local binary="$1" json status
  set +e
  json="$("$binary" app-server daemon version 2>/dev/null)"
  local rc=$?
  set -e
  (( rc == 0 )) || return 1

  status="$(python3 -c 'import json,sys
try:
    print(json.load(sys.stdin).get("status",""))
except Exception:
    pass' <<<"$json" 2>/dev/null || true)"
  case "$status" in
    running|alreadyRunning|started|restarted) return 0 ;;
    *) return 1 ;;
  esac
}

wait_for_lock_free() {
  local lock_file="$1" seconds="\${2:-10}" i
  for ((i=0; i<seconds*10; i++)); do
    lock_is_free "$lock_file" && return 0
    sleep 0.1
  done
  return 1
}

terminate_managed_holders() {
  local lock_file="$1" pids pid remaining
  pids="$(lock_holder_pids "$lock_file" | sort -u)"
  [[ -n "$pids" ]] || return 1

  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    if ! is_managed_daemon_holder "$pid"; then
      warn "refusing to terminate unknown lock holder PID $pid: $(pid_cmdline "$pid")"
      return 1
    fi
  done <<<"$pids"

  warn "legacy managed Codex daemon still holds codex-tool lock; sending TERM to: $(tr '\n' ' ' <<<"$pids" | sed 's/[[:space:]]\+/ /g')"
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    kill -TERM "$pid" 2>/dev/null || true
  done <<<"$pids"

  wait_for_lock_free "$lock_file" 5 && return 0

  remaining="$(lock_holder_pids "$lock_file" | sort -u)"
  [[ -n "$remaining" ]] || return 1
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    is_managed_daemon_holder "$pid" || return 1
  done <<<"$remaining"

  warn "legacy managed daemon did not release the lock after TERM; sending KILL to: $(tr '\n' ' ' <<<"$remaining" | sed 's/[[:space:]]\+/ /g')"
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    kill -KILL "$pid" 2>/dev/null || true
  done <<<"$remaining"

  wait_for_lock_free "$lock_file" 5
}

recover_legacy_manager_locks() {
  need_cmd flock
  need_cmd stat
  need_cmd python3

  local lock_file pids pid binary=""
  local saw_stale_daemon=0

  while IFS= read -r lock_file; do
    [[ -n "$lock_file" ]] || continue
    [[ -e "$lock_file" || -L "$lock_file" ]] || continue

    if lock_is_free "$lock_file"; then
      continue
    fi

    pids="$(lock_holder_pids "$lock_file" | sort -u)"
    if [[ -z "$pids" ]]; then
      die "manager lock is busy but its holder could not be identified safely: $lock_file"
    fi

    while IFS= read -r pid; do
      [[ -n "$pid" ]] || continue
      if is_codex_tool_holder "$pid"; then
        die "another codex-tool operation is still running (PID $pid): $(pid_cmdline "$pid")"
      fi
      if ! is_managed_daemon_holder "$pid"; then
        die "manager lock is held by an unknown process (PID $pid): $(pid_cmdline "$pid")"
      fi
    done <<<"$pids"

    saw_stale_daemon=1
    warn "detected manager lock inherited by legacy managed Codex daemon: $lock_file"
    warn "holder PID(s): $(tr '\n' ' ' <<<"$pids" | sed 's/[[:space:]]\+/ /g')"

    if [[ -z "$binary" ]]; then
      binary="$(find_daemon_control_binary 2>/dev/null || true)"
      if [[ -n "$binary" ]] && daemon_reports_running "$binary"; then
        RESTART_DAEMON_AFTER_INSTALL=1
      else
        # A live managed daemon holder means the old runtime was active even if
        # its control socket/version query is already stale.
        RESTART_DAEMON_AFTER_INSTALL=1
      fi

      if [[ -n "$binary" ]]; then
        log "stopping managed Codex daemon to release legacy codex-tool lock"
        if ! "$binary" app-server daemon stop >/dev/null 2>&1; then
          warn "official daemon stop did not complete; installer will fall back to verified managed-holder termination"
        fi
      fi
    fi

    if ! wait_for_lock_free "$lock_file" 10; then
      terminate_managed_holders "$lock_file" \
        || die "unable to release legacy codex-tool manager lock safely: $lock_file"
    fi

    lock_is_free "$lock_file" \
      || die "legacy codex-tool manager lock is still held after recovery: $lock_file"

    log "released legacy codex-tool manager lock: $lock_file"
  done < <(manager_lock_files | awk '!seen[$0]++')

  (( saw_stale_daemon )) || return 0
}

restart_managed_daemon_if_needed() {
  (( RESTART_DAEMON_AFTER_INSTALL )) || return 0

  local binary=""
  binary="$(find_daemon_control_binary 2>/dev/null || true)"
  if [[ -z "$binary" ]]; then
    warn "legacy daemon lock was released, but no daemon-capable Codex binary is available to restore the daemon"
    return 0
  fi

  log "restoring managed Codex daemon after legacy-lock recovery"
  if ! "$binary" app-server daemon start >/dev/null 2>&1; then
    warn "Codex daemon could not be restarted automatically; it will be started again by Codex when needed"
  fi
}

recover_legacy_manager_locks

mkdir -p "$TOOL_HOME" "$TOOL_HOME/versions" "$TOOL_HOME/downloads" "$BIN_DIR"
install -m 0755 "$SRC_DIR/codex-tool" "$TOOL_HOME/codex-tool"
[[ ! -f "$SRC_DIR/README.md" ]] || install -m 0644 "$SRC_DIR/README.md" "$TOOL_HOME/README.md"

LINK="$BIN_DIR/codex-tool"
if [[ -e "$LINK" || -L "$LINK" ]]; then
  if [[ -L "$LINK" ]]; then
    raw="$(readlink "$LINK" 2>/dev/null || true)"
    resolved="$(readlink -f "$LINK" 2>/dev/null || true)"
    expected="$(readlink -f "$TOOL_HOME/codex-tool")"
    if [[ "$resolved" != "$expected" && "$raw" != *"/scripts/codex-tool/codex-tool" && "$FORCE" != "1" ]]; then
      die "$LINK exists and is not managed by codex-tool; use --force to replace it"
    fi
  elif [[ "$FORCE" != "1" ]]; then
    die "$LINK exists and is not a symlink; use --force to replace it"
  fi
fi
ln -sfn "$TOOL_HOME/codex-tool" "$LINK"

PROFILE="$HOME/.bashrc"
PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'
if [[ "$BIN_DIR" == "$HOME/.local/bin" ]] && ! grep -Fqs '$HOME/.local/bin' "$PROFILE" 2>/dev/null; then
  printf '\n# Added by codex-tool installer\n%s\n' "$PATH_LINE" >> "$PROFILE"
  log "added ~/.local/bin to PATH in ~/.bashrc"
fi

restart_managed_daemon_if_needed

log "installed codex-tool to $TOOL_HOME/codex-tool"
log "command link: $LINK"
log "existing versions, current selection, download cache, and ~/.codex user data were preserved"
log "run: export PATH=\"$BIN_DIR:\$PATH\" && codex-tool version"
