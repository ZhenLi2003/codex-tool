#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

TOOL_HOME="${CODEX_TOOL_HOME:-$HOME/scripts/codex-tool}"
BIN_DIR="${CODEX_TOOL_BIN_DIR:-$HOME/.local/bin}"
FORCE=0
[[ "${1:-}" != "--force" ]] || { FORCE=1; shift; }
[[ $# -eq 0 ]] || { echo "usage: ./install.sh [--force]" >&2; exit 2; }

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ -x "$SRC_DIR/codex-tool" ]] || { echo "error: codex-tool payload is missing" >&2; exit 1; }

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
      echo "error: $LINK exists and is not managed by codex-tool; use --force to replace it" >&2
      exit 1
    fi
  elif [[ "$FORCE" != "1" ]]; then
    echo "error: $LINK exists and is not a symlink; use --force to replace it" >&2
    exit 1
  fi
fi
ln -sfn "$TOOL_HOME/codex-tool" "$LINK"

PROFILE="$HOME/.bashrc"
PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'
if [[ "$BIN_DIR" == "$HOME/.local/bin" ]] && ! grep -Fqs '$HOME/.local/bin' "$PROFILE" 2>/dev/null; then
  printf '\n# Added by codex-tool installer\n%s\n' "$PATH_LINE" >> "$PROFILE"
  echo "==> added ~/.local/bin to PATH in ~/.bashrc"
fi

echo "==> installed codex-tool to $TOOL_HOME/codex-tool"
echo "==> command link: $LINK"
echo "==> existing versions, current selection, download cache, and ~/.codex data were preserved"
echo "==> run: export PATH=\"$BIN_DIR:\$PATH\" && codex-tool version"
