#!/usr/bin/env bash
set -Eeuo pipefail
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
export HOME="$scratch/home"
mkdir -p "$HOME"
export CODEX_TOOL_HOME="$HOME/scripts/codex-tool"
export CODEX_TOOL_BIN_DIR="$HOME/.local/bin"
export CODEX_HOME="$HOME/.codex"
export CODEX_TOOL_CONFIG_DIR="$HOME/.config/codex-tool"
bash ./install.sh >/dev/null
test -f "$CODEX_TOOL_HOME/background_v2.py"
test -f "$CODEX_TOOL_HOME/vendor/tomlkit/parser.py"
test -f "$CODEX_TOOL_HOME/vendor/tomlkit.LICENSE"
test "$("$CODEX_TOOL_HOME/codex-tool" version)" = 'codex-tool 2.2.0'
"$CODEX_TOOL_HOME/codex-tool" background status --json > "$scratch/status.json"
python3 - "$scratch/status.json" <<'PY'
import json, sys
state=json.load(open(sys.argv[1],encoding='utf-8'))
assert state['config'] == 'native-compatible', state
assert 'runtime' in state and 'launcher' in state and 'health' in state, state
assert state['api_ok'] is False
PY
# A repeat manager install must preserve user files and carry its own parser.
bash ./install.sh >/dev/null
python3 "$CODEX_TOOL_HOME/background_v2.py" --help > /dev/null
printf '%s\n' 'non-root offline installer and live status smoke test passed'
