#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
TMP="$(mktemp -d)"
trap 'rm -rf -- "$TMP"' EXIT

# Source definitions only; do not dispatch the real manager CLI.
# shellcheck disable=SC1090
source <(sed '/^main "\$@"$/d' "$REPO_ROOT/codex-tool")

PACKAGE_ASSET="test-codex-package.tar.gz"
url="https://github.com/openai/codex/releases/download/rust-v1.2.3/$PACKAGE_ASSET"
complete="$TMP/$PACKAGE_ASSET"
partial="$complete.part"
printf '%s' 'verified package fixture' > "$TMP/fixture"
sha="$(sha256sum "$TMP/fixture" | awk '{print $1}')"

test_output="$(print_download_instructions 1.2.3 "$url" "$sha" "$complete")"
[[ "$test_output" == *"$url"* ]]
[[ "$test_output" == *"$complete"* ]]
[[ "$test_output" == *"$sha"* ]]

resumable_download() {
  printf '%s\n' "$*" >> "$TMP/calls"
  cp -- "$TMP/fixture" "$2"
}

# Full local package must take precedence over an existing partial download.
cp "$TMP/fixture" "$complete"
printf 'partial bytes' > "$partial"
select_local_or_remote_package "$url" "$complete" "$partial" "$sha"
[[ "$SELECTED_ARCHIVE" == "$complete" ]]
[[ ! -e "$TMP/calls" ]]

# With no complete package, the original resumable downloader is invoked.
rm -- "$complete"
select_local_or_remote_package "$url" "$complete" "$partial" "$sha"
[[ "$SELECTED_ARCHIVE" == "$partial" ]]
[[ -s "$TMP/calls" ]]

# A corrupt manually uploaded file must be preserved and must not fall back.
printf 'bad upload' > "$complete"
before="$(wc -l < "$TMP/calls")"
if (select_local_or_remote_package "$url" "$complete" "$partial" "$sha") >"$TMP/bad.log" 2>&1; then
  echo "ERROR: corrupt upload was accepted" >&2
  exit 1
fi
[[ -f "$complete" ]]
[[ "$before" == "$(wc -l < "$TMP/calls")" ]]
grep -q 'manual package SHA-256 mismatch' "$TMP/bad.log"

# Never follow a symlink offered as the complete local archive.
rm -- "$complete"
ln -s "$TMP/fixture" "$complete"
if (select_local_or_remote_package "$url" "$complete" "$partial" "$sha") >"$TMP/link.log" 2>&1; then
  echo "ERROR: symlink upload was accepted" >&2
  exit 1
fi
grep -q 'regular non-symlink file' "$TMP/link.log"
rm -- "$complete"

# A corrupt network .part is removed; a correct upload remains untouched.
resumable_download() {
  printf '%s' 'corrupt network content' > "$2"
}
if (select_local_or_remote_package "$url" "$complete" "$partial" "$sha") >"$TMP/partial.log" 2>&1; then
  echo "ERROR: corrupt automatic download was accepted" >&2
  exit 1
fi
[[ ! -e "$partial" ]]
grep -q 'removing corrupted partial file' "$TMP/partial.log"

echo "manual-download and resumable-download tests passed"
