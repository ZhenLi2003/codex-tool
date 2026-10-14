#!/usr/bin/env python3
"""Conservative, standard-library-only Codex background policy manager."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile

ROOT_KEY = ("", "check_for_update_on_startup")
FEATURE_KEY = ("features", "daemon_auto_start")
KEYS = {ROOT_KEY: "false", FEATURE_KEY: "false"}
SETTINGS_FIELDS = (
    ("remoteControlEnabled",),
    ("updater", "autoUpdateEnabled"),
)
HEADER = re.compile(r"^\s*\[([^\]]+)\]\s*(?:#.*)?$")
ASSIGN = re.compile(r"^(\s*)([A-Za-z0-9_.-]+)(\s*=\s*)(.*?)(\r?\n?)$")


def fail(message: str) -> None:
    raise ValueError(message)


def private_dir(path: Path) -> None:
    if path.is_symlink():
        fail(f"refusing symlink directory: {path}")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not path.is_dir() or path.stat().st_uid != os.getuid():
        fail(f"background directory has unsafe ownership: {path}")
    path.chmod(0o700)


def load_text(path: Path) -> tuple[bool, str, int]:
    if path.is_symlink():
        fail(f"refusing to edit symlink: {path}")
    if not path.exists():
        return False, "", 0o600
    if not path.is_file():
        fail(f"not a regular file: {path}")
    if path.stat().st_uid != os.getuid():
        fail(f"file is not owned by current user: {path}")
    return True, path.read_bytes().decode("utf-8"), stat.S_IMODE(path.stat().st_mode)


def atomic_write(path: Path, content: str, mode: int = 0o600) -> None:
    private_dir(path.parent)
    if path.is_symlink():
        fail(f"refusing symlink target: {path}")
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def toml_entries(text: str) -> tuple[list[str], dict[tuple[str, str], list[int]], dict[str, int]]:
    lines = text.splitlines(keepends=True)
    scope = ""
    entries: dict[tuple[str, str], list[int]] = {}
    headers: dict[str, int] = {}
    for i, line in enumerate(lines):
        h = HEADER.match(line.strip())
        if h:
            scope = h.group(1).strip()
            headers[scope] = i
            continue
        m = ASSIGN.match(line)
        if not m or line.lstrip().startswith("#"):
            continue
        key = m.group(2)
        if scope == "" and key == "features.daemon_auto_start":
            target = FEATURE_KEY
        else:
            target = (scope, key)
        if target in KEYS:
            entries.setdefault(target, []).append(i)
        # Inline features objects cannot safely be modified with line-based edits.
        if scope == "" and key == "features" and m.group(4).lstrip().startswith("{"):
            fail("inline 'features = {...}' is unsupported; use [features] or Codex config API")
    for key in KEYS:
        if len(entries.get(key, [])) > 1:
            fail(f"duplicate TOML setting: {key}")
    return lines, entries, headers


def right_hand_side(line: str) -> str:
    m = ASSIGN.match(line)
    if not m:
        fail(f"cannot parse TOML boolean setting: {line.strip()}")
    value = m.group(4).split("#", 1)[0].strip()
    if value not in ("true", "false"):
        fail(f"expected boolean value, found {value!r}")
    return value


def modify_toml(text: str, originals: dict | None, *, optimize: bool) -> tuple[str, dict]:
    # Process one key at a time and reparse after each mutation because indices move.
    snapshot: dict = {} if originals is None else originals
    for scope, key in KEYS:
        identifier = f"{scope}.{key}" if scope else key
        lines, entries, headers = toml_entries(text)
        positions = entries.get((scope, key), [])
        if optimize:
            if identifier not in snapshot:
                snapshot[identifier] = {
                    "present": bool(positions),
                    "line": lines[positions[0]] if positions else None,
                }
            if positions:
                index = positions[0]
                m = ASSIGN.match(lines[index])
                assert m
                lines[index] = f"{m.group(1)}{m.group(2)}{m.group(3)}false{m.group(5)}"
            else:
                if scope == "":
                    first_header = next((i for i, line in enumerate(lines) if HEADER.match(line.strip())), len(lines))
                    lines.insert(first_header, f"{key} = false\n")
                elif scope in headers:
                    lines.insert(headers[scope] + 1, f"{key} = false\n")
                else:
                    if lines and not lines[-1].endswith("\n"):
                        lines[-1] += "\n"
                    if lines and lines[-1].strip():
                        lines.append("\n")
                    lines.extend([f"[{scope}]\n", f"{key} = false\n"])
        else:
            info = snapshot.get(identifier)
            if info is None:
                fail(f"missing backup metadata for {identifier}")
            if not positions:
                fail(f"managed setting disappeared: {identifier}")
            if right_hand_side(lines[positions[0]]) != "false":
                fail(f"managed setting was changed externally: {identifier}")
            if info["present"]:
                lines[positions[0]] = info["line"]
            else:
                lines.pop(positions[0])
        text = "".join(lines)
    return text, snapshot


def get_nested(mapping: dict, path: tuple[str, ...]) -> tuple[bool, object]:
    cur: object = mapping
    for part in path:
        if not isinstance(cur, dict) or part not in cur:
            return False, None
        cur = cur[part]
    return True, cur


def set_nested(mapping: dict, path: tuple[str, ...], value: object, present: bool = True) -> None:
    cur = mapping
    for part in path[:-1]:
        child = cur.get(part)
        if child is None:
            child = {}
            cur[part] = child
        if not isinstance(child, dict):
            fail(f"JSON setting parent is not an object: {path}")
        cur = child
    if present:
        cur[path[-1]] = value
    else:
        cur.pop(path[-1], None)
        if not cur and len(path) > 1:
            mapping.pop(path[0], None)


def modify_settings(text: str, originals: dict | None, *, optimize: bool) -> tuple[str, dict]:
    value = json.loads(text) if text.strip() else {}
    if not isinstance(value, dict):
        fail("daemon settings JSON root must be an object")
    snapshot: dict = {} if originals is None else originals
    for path in SETTINGS_FIELDS:
        name = ".".join(path)
        present, old = get_nested(value, path)
        if optimize:
            if name not in snapshot:
                snapshot[name] = {"present": present, "value": old}
            set_nested(value, path, False)
        else:
            meta = snapshot.get(name)
            if meta is None:
                fail(f"missing backup metadata for {name}")
            current_present, current = get_nested(value, path)
            if not current_present or current is not False:
                fail(f"managed JSON setting was changed externally: {name}")
            set_nested(value, path, meta["value"], bool(meta["present"]))
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n", snapshot


def paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    return (
        Path(args.codex_home) / "config.toml",
        Path(args.codex_home) / "app-server-daemon" / "settings.json",
        Path(args.config_dir) / "background",
    )


def status(args: argparse.Namespace) -> int:
    conf, settings, policy = paths(args)
    manifest = policy / "manifest.json"
    state = "optimized" if manifest.exists() else "native"
    _, config_text, _ = load_text(conf)
    _, settings_text, _ = load_text(settings)
    _, entries, _ = toml_entries(config_text)
    values = {}
    for key in KEYS:
        places = entries.get(key, [])
        name = f"{key[0]}.{key[1]}" if key[0] else key[1]
        values[name] = right_hand_side(config_text.splitlines(keepends=True)[places[0]]) if places else "unset"
    mapping = json.loads(settings_text) if settings_text.strip() else {}
    for path in SETTINGS_FIELDS:
        present, val = get_nested(mapping, path)
        values[".".join(path)] = val if present else "unset"
    print(json.dumps({"mode": state, "configuration": values}, ensure_ascii=False))
    return 0


def apply(args: argparse.Namespace, optimize: bool) -> int:
    conf, settings, policy = paths(args)
    manifest_path = policy / "manifest.json"
    if optimize and manifest_path.exists():
        print("Background optimization is already configured.")
        return 0
    if not optimize and not manifest_path.exists():
        print("Native mode is already configured.")
        return 0

    config_existed, old_config, config_mode = load_text(conf)
    settings_existed, old_settings, settings_mode = load_text(settings)

    if optimize:
        new_config, toml_originals = modify_toml(old_config, None, optimize=True)
        new_settings, json_originals = modify_settings(old_settings, None, optimize=True)
        _, original_entries, original_headers = toml_entries(old_config)
        manifest = {
            "schema": 1,
            "features_header_existed": "features" in original_headers,
            "config_existed": config_existed,
            "settings_existed": settings_existed,
            "config_mode": config_mode,
            "settings_mode": settings_mode,
            "toml_originals": toml_originals,
            "json_originals": json_originals,
        }
        private_dir(policy)
        backup = policy / "backup"
        private_dir(backup)
        atomic_write(backup / "config.toml", old_config, 0o600)
        atomic_write(backup / "daemon-settings.json", old_settings, 0o600)
    else:
        if manifest_path.is_symlink():
            fail("refusing symlink policy manifest")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema") != 1:
            fail("unsupported background manifest schema")
        new_config, _ = modify_toml(old_config, manifest["toml_originals"], optimize=False)
        new_settings, _ = modify_settings(old_settings, manifest["json_originals"], optimize=False)

        if not manifest.get("features_header_existed", True):
            # The manager may have introduced an otherwise empty [features] table.
            # Remove only a wholly empty table; preserve comments and new user keys.
            lines = new_config.splitlines(keepends=True)
            for index, line in enumerate(lines):
                if not re.match(r"^\s*\[features\]\s*$", line.strip()):
                    continue
                end = next((j for j in range(index + 1, len(lines))
                            if HEADER.match(lines[j].strip())), len(lines))
                if all(not row.strip() for row in lines[index + 1:end]):
                    del lines[index:end]
                break
            new_config = "".join(lines)

        # If the result has exactly the original logical lines, keep byte-for-byte
        # formatting from the protected initial backup.
        backup_config = policy / "backup" / "config.toml"
        if backup_config.exists():
            backed_up = backup_config.read_bytes().decode("utf-8")
            if new_config.strip() == backed_up.strip():
                new_config = backed_up

    # Validate both changes before writing either file.
    original1 = (config_existed, old_config, config_mode)
    original2 = (settings_existed, old_settings, settings_mode)
    try:
        if not optimize and not manifest["config_existed"] and not new_config.strip():
            conf.unlink(missing_ok=True)
        else:
            atomic_write(conf, new_config, config_mode)
        if not optimize and not manifest["settings_existed"] and json.loads(new_settings) == {}:
            settings.unlink(missing_ok=True)
        else:
            atomic_write(settings, new_settings, settings_mode)
        if optimize:
            atomic_write(manifest_path, json.dumps(manifest, indent=2) + "\n", 0o600)
        else:
            manifest_path.unlink()
            for name in ("config.toml", "daemon-settings.json"):
                (policy / "backup" / name).unlink(missing_ok=True)
    except Exception:
        for path, (existed, content, mode) in ((conf, original1), (settings, original2)):
            if existed:
                atomic_write(path, content, mode)
            else:
                path.unlink(missing_ok=True)
        raise

    print("Applied background optimization." if optimize else "Restored native background configuration.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["status", "optimize", "native"])
    parser.add_argument("--codex-home", required=True)
    parser.add_argument("--config-dir", required=True)
    args = parser.parse_args()
    try:
        if args.action == "status":
            return status(args)
        return apply(args, optimize=args.action == "optimize")
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"background policy error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
