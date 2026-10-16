#!/usr/bin/env python3
"""Conservative, standard-library-only Codex background policy manager."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

try:
    import tomllib  # Python 3.11+; validate the full document before edits
except ImportError:
    tomllib = None

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


def validate_toml(text: str) -> None:
    if tomllib is not None and text.strip():
        try:
            tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            fail(f"invalid Codex config.toml: {exc}")


def toml_entries(text: str) -> tuple[list[str], dict[tuple[str, str], list[int]], dict[str, int]]:
    validate_toml(text)
    lines = text.splitlines(keepends=True)
    scope = ""
    entries: dict[tuple[str, str], list[int]] = {}
    headers: dict[str, int] = {}
    for i, line in enumerate(lines):
        h = HEADER.match(line.strip())
        if h:
            scope = h.group(1).strip()
            if scope in headers:
                fail(f"duplicate TOML table: {scope}")
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
        fail(f"expected TOML boolean value, found {value!r}")
    return value


def toml_snapshot(text: str) -> dict:
    lines, entries, _ = toml_entries(text)
    result = {}
    for scope, key in KEYS:
        name = f"{scope}.{key}" if scope else key
        indices = entries.get((scope, key), [])
        result[name] = {
            "present": bool(indices),
            "value": right_hand_side(lines[indices[0]]) == "true" if indices else None,
        }
    return result


def modified_bool_line(line: str, value: bool) -> str:
    match = ASSIGN.match(line)
    if not match:
        fail(f"cannot modify TOML boolean line: {line.strip()}")
    right = match.group(4)
    m = re.match(r"^(\s*)(true|false)(\s*(?:#.*)?)$", right)
    if not m:
        fail(f"unsupported managed TOML value: {line.strip()}")
    replacement = "true" if value else "false"
    return f"{match.group(1)}{match.group(2)}{match.group(3)}{m.group(1)}{replacement}{m.group(3)}{match.group(5)}"


MANAGED_COMMENTS = {
    ROOT_KEY: "# codex-tool: Disable automatic CLI update checks; use codex-tool update.",
    FEATURE_KEY: "# codex-tool: Prevent ordinary Codex sessions from auto-starting the shared daemon.",
}


def newline_for(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def insert_managed_setting(
    lines: list[str], scope: str, key: str, setting_line: str,
    comment_line: str | None = None,
) -> None:
    """Insert a root key or an entry into an existing/new section without moving other keys."""
    text = "".join(lines)
    _, _, headers = toml_entries(text)
    nl = newline_for(text)
    prefix = [comment_line + nl] if comment_line else []
    if not setting_line.endswith(("\n", "\r\n")):
        setting_line += nl
    payload = prefix + [setting_line]
    if scope == "":
        first_header = next((i for i, line in enumerate(lines) if HEADER.match(line.strip())), len(lines))
        # Keep the whitespace that already separates the root and the first table
        # after the newly inserted key, rather than introducing extra empty lines.
        index = first_header
        while index > 0 and not lines[index - 1].strip():
            index -= 1
        if index == len(lines) and lines and not lines[-1].endswith("\n"):
            lines[-1] += nl
        lines[index:index] = payload
        if first_header < len(lines) - len(payload) and not lines[index + len(payload)].strip():
            return
        if any(HEADER.match(line.strip()) for line in lines[index + len(payload):]):
            if index + len(payload) < len(lines) and lines[index + len(payload)].strip():
                lines.insert(index + len(payload), nl)
    elif scope in headers:
        lines[headers[scope] + 1:headers[scope] + 1] = payload
    else:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += nl
        if lines and lines[-1].strip():
            lines.append(nl)
        lines.extend([f"[{scope}]{nl}"] + payload)


def remove_manager_comments(lines: list[str]) -> None:
    exact = set(MANAGED_COMMENTS.values())
    lines[:] = [line for line in lines if line.strip() not in exact]


def tidy_managed_tables(lines: list[str]) -> None:
    """Ensure a single empty line at [features] section boundaries only."""
    text = "".join(lines)
    nl = newline_for(text)
    section_indices = [
        (i, HEADER.match(row.strip()).group(1).strip())
        for i, row in enumerate(lines) if HEADER.match(row.strip())
    ]
    features = next((i for i, name in section_indices if name == "features"), None)
    if features is None:
        return

    # Separator before [features]: do not move unrelated keys or user comments.
    if features > 0:
        start = features
        while start > 0 and not lines[start - 1].strip():
            start -= 1
        if start == features:
            lines.insert(features, nl)
            features += 1
        elif start > 0 and features - start != 1:
            del lines[start + 1:features]
            features = start + 1

    # Separator after the [features] table, before the next TOML table.
    following = next(
        (i for i in range(features + 1, len(lines)) if HEADER.match(lines[i].strip())),
        None,
    )
    if following is None or following == 0:
        return
    start = following
    while start > 0 and not lines[start - 1].strip():
        start -= 1
    if start == following:
        # If a user comment is directly before the next heading, do not detach
        # that comment; Codex-owned formatting is restricted to the features table.
        if not lines[following - 1].lstrip().startswith("#"):
            lines.insert(following, nl)
    elif start > 0 and following - start != 1:
        del lines[start + 1:following]


def modify_toml(text: str, originals: dict | None, *, optimize: bool) -> tuple[str, dict]:
    """Managed field reconciliation with exact original backup and annotated edits."""
    snapshot: dict = {} if originals is None else originals
    for scope, key in KEYS:
        identifier = f"{scope}.{key}" if scope else key
        lines, entries, _ = toml_entries(text)
        positions = entries.get((scope, key), [])
        if optimize:
            if identifier not in snapshot:
                snapshot[identifier] = {
                    "present": bool(positions),
                    "line": lines[positions[0]] if positions else None,
                }
            if positions:
                i = positions[0]
                lines[i] = modified_bool_line(lines[i], False)
                if i == 0 or lines[i - 1].strip() != MANAGED_COMMENTS[(scope, key)]:
                    lines.insert(i, MANAGED_COMMENTS[(scope, key)] + newline_for(text))
            else:
                insert_managed_setting(
                    lines, scope, key, f"{key} = false",
                    MANAGED_COMMENTS[(scope, key)],
                )
        else:
            info = snapshot.get(identifier)
            if info is None:
                fail(f"missing original backup metadata for {identifier}")
            # Drop only tool-owned explanatory comments, not any user's comments.
            remove_manager_comments(lines)
            lines, entries, _ = toml_entries("".join(lines))
            positions = entries.get((scope, key), [])
            if info["present"]:
                desired = right_hand_side(info["line"]) == "true"
                if positions:
                    if (right_hand_side(lines[positions[0]]) == "true") != desired:
                        lines[positions[0]] = info["line"]
                else:
                    insert_managed_setting(lines, scope, key, info["line"])
            elif positions:
                lines.pop(positions[0])
        text = "".join(lines)
    lines = text.splitlines(keepends=True)
    if optimize:
        tidy_managed_tables(lines)
    else:
        remove_manager_comments(lines)
    text = "".join(lines)
    validate_toml(text)
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
    changed = False
    for path in SETTINGS_FIELDS:
        name = ".".join(path)
        present, old = get_nested(value, path)
        if optimize:
            if name not in snapshot:
                snapshot[name] = {"present": present, "value": old}
            if not present or old is not False:
                set_nested(value, path, False)
                changed = True
        else:
            meta = snapshot.get(name)
            if meta is None:
                fail(f"missing original backup metadata for {name}")
            target_present, target_value = bool(meta["present"]), meta["value"]
            if present != target_present or (present and old != target_value):
                set_nested(value, path, target_value, target_present)
                changed = True
    if not changed:
        return text, snapshot
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n", snapshot


def paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    return (
        Path(args.codex_home) / "config.toml",
        Path(args.codex_home) / "app-server-daemon" / "settings.json",
        Path(args.config_dir) / "background",
    )


def settings_snapshot(text: str) -> dict:
    mapping = json.loads(text) if text.strip() else {}
    if not isinstance(mapping, dict):
        fail("daemon settings JSON root must be an object")
    result = {}
    for path in SETTINGS_FIELDS:
        present, value = get_nested(mapping, path)
        result[".".join(path)] = {"present": present, "value": value if present else None}
    return result


def original_snapshots(manifest: dict) -> tuple[dict, dict]:
    toml_originals = {}
    for name, info in manifest["toml_originals"].items():
        toml_originals[name] = {
            "present": info["present"],
            "value": right_hand_side(info["line"]) == "true" if info["present"] else None,
        }
    json_originals = {}
    for name, info in manifest["json_originals"].items():
        json_originals[name] = {
            "present": info["present"],
            "value": info["value"] if info["present"] else None,
        }
    return toml_originals, json_originals


def managed_applied() -> dict:
    keys = {f"{scope}.{key}" if scope else key: {"present": True, "value": False}
            for scope, key in KEYS}
    settings = {".".join(path): {"present": True, "value": False}
                for path in SETTINGS_FIELDS}
    return {"toml": keys, "json": settings}


def read_manifest(path: Path) -> dict | None:
    if path.is_symlink():
        fail(f"refusing symlink manifest: {path}")
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_uid != os.getuid():
        fail(f"unsafe background manifest: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") not in (1, 2):
        fail("invalid or unsupported background manifest schema")
    original_toml, original_json = original_snapshots(value)
    originals = {"toml": original_toml, "json": original_json}
    expected = managed_applied()
    for group in ("toml", "json"):
        if set(originals[group]) != set(expected[group]):
            fail(f"background manifest missing managed keys in {group}")
    if value["schema"] == 2 and value.get("applied") != expected:
        fail("background manifest has unsupported applied settings")
    return value


def observed_state(config_text: str, settings_text: str) -> dict:
    return {"toml": toml_snapshot(config_text), "json": settings_snapshot(settings_text)}


def compare_state(current: dict, desired: dict, original: dict | None) -> list[dict]:
    rows = []
    for group in ("toml", "json"):
        for name, target in desired[group].items():
            actual = current[group][name]
            if actual == target:
                continue
            initial = original[group][name] if original else None
            rows.append({
                "file": "config.toml" if group == "toml" else "app-server-daemon/settings.json",
                "key": name,
                "current": actual,
                "target": target,
                "original": initial,
                "classification": (
                    "original-already-restored" if original and actual == initial
                    else "external-conflict"
                ),
            })
    return rows


def report(args: argparse.Namespace) -> dict:
    conf, settings, policy = paths(args)
    manifest = read_manifest(policy / "manifest.json")
    _, config_text, _ = load_text(conf)
    _, settings_text, _ = load_text(settings)
    current = observed_state(config_text, settings_text)
    applied = managed_applied()
    original = None
    if manifest:
        t, j = original_snapshots(manifest)
        original = {"toml": t, "json": j}

    if args.action == "status":
        drift = compare_state(current, applied, original) if manifest else []
        values = {**{k: (v["value"] if v["present"] else "unset") for k,v in current["toml"].items()},
                  **{k: (v["value"] if v["present"] else "unset") for k,v in current["json"].items()}}
        return {
            "mode": "optimized" if manifest else "native",
            "effective": ("modified" if drift else "optimized") if manifest else "native",
            "configuration": values,
            "drift": drift,
            "manifest_schema": manifest.get("schema") if manifest else None,
        }

    target = args.target if args.action == "check" else args.action
    if target not in ("optimize", "native"):
        fail(f"invalid background target: {target}")

    if target == "optimize":
        differences = compare_state(current, applied, original) if manifest else []
        needs_confirmation = bool(differences)
    else:
        differences = compare_state(current, original, original) if original else []
        # A current value equal to Applied or Original is always safe to restore.
        needs_confirmation = any(
            row["current"] != applied[
                "toml" if row["file"] == "config.toml" else "json"
            ][row["key"]]
            for row in differences
        )
    return {
        "target": target,
        "mode": "optimized" if manifest else "native",
        "changes": differences,
        "confirmation_required": needs_confirmation,
        "manifest_schema": manifest.get("schema") if manifest else None,
    }


def status(args: argparse.Namespace) -> int:
    print(json.dumps(report(args), ensure_ascii=False, sort_keys=True))
    return 0


def stage_manifest_upgrade(manifest: dict) -> dict:
    if manifest.get("schema") == 2:
        return manifest
    upgraded = dict(manifest)
    upgraded["schema"] = 2
    upgraded["mode"] = "optimized"
    upgraded["applied"] = managed_applied()
    return upgraded


def unchanged(path: Path, initial: tuple[bool, str, int]) -> bool:
    existed, content, mode = load_text(path)
    return (existed, content, mode) == initial


def apply(args: argparse.Namespace, optimize: bool) -> int:
    conf, settings, policy = paths(args)
    manifest_path = policy / "manifest.json"
    existing = read_manifest(manifest_path)
    if not optimize and existing is None:
        print("Native mode is already configured.")
        return 0

    config_initial = load_text(conf)
    settings_initial = load_text(settings)
    config_existed, old_config, config_mode = config_initial
    settings_existed, old_settings, settings_mode = settings_initial
    current = observed_state(old_config, old_settings)
    applied = managed_applied()
    originals = None
    if existing:
        orig_t, orig_j = original_snapshots(existing)
        originals = {"toml": orig_t, "json": orig_j}

    target = applied if optimize else originals
    changes = compare_state(current, target, originals) if target else []
    if optimize:
        confirmation_required = bool(changes) and existing is not None
    else:
        confirmation_required = any(
            row["current"] != applied["toml" if row["file"] == "config.toml" else "json"][row["key"]]
            for row in changes
        )
    if confirmation_required and not args.yes:
        keys = ", ".join(row["key"] for row in changes)
        fail(f"managed fields were modified externally: {keys}; confirm with --yes after reviewing 'background status'")

    if optimize:
        new_config, toml_originals = modify_toml(
            old_config, existing["toml_originals"] if existing else None, optimize=True
        )
        new_settings, json_originals = modify_settings(
            old_settings, existing["json_originals"] if existing else None, optimize=True
        )
        if existing:
            manifest = stage_manifest_upgrade(existing)
        else:
            _, _, original_headers = toml_entries(old_config)
            manifest = {
                "schema": 2,
                "mode": "optimized",
                "applied": applied,
                "features_header_existed": "features" in original_headers,
                "config_existed": config_existed,
                "settings_existed": settings_existed,
                "config_mode": config_mode,
                "settings_mode": settings_mode,
                "toml_originals": toml_originals,
                "json_originals": json_originals,
            }
    else:
        manifest = existing
        new_config, _ = modify_toml(old_config, manifest["toml_originals"], optimize=False)
        new_settings, _ = modify_settings(old_settings, manifest["json_originals"], optimize=False)

        if not manifest.get("features_header_existed", True):
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

        backup_config = policy / "backup" / "config.toml"
        if backup_config.is_file() and not backup_config.is_symlink():
            backed_up = backup_config.read_text(encoding="utf-8")
            if new_config.strip() == backed_up.strip():
                new_config = backed_up

    # Fail before any write if another process edited either file since reading it.
    if not unchanged(conf, config_initial) or not unchanged(settings, settings_initial):
        fail("Codex configuration changed during background reconciliation; retry")

    # A no-op repeated optimize retains the original backups, even with unrelated edits.
    if (optimize and existing and new_config == old_config and new_settings == old_settings
            and existing.get("schema") == 2):
        print("Background optimization verified; no changes required.")
        return 0

    try:
        if optimize and existing is None:
            private_dir(policy)
            backup = policy / "backup"
            private_dir(backup)
            atomic_write(backup / "config.toml", old_config, 0o600)
            atomic_write(backup / "daemon-settings.json", old_settings, 0o600)
        else:
            # Never rewrite the protected first-optimization backups.
            pass

        if new_config != old_config:
            if not optimize and not manifest["config_existed"] and not new_config.strip():
                conf.unlink(missing_ok=True)
            else:
                atomic_write(conf, new_config, config_mode)
        if not unchanged(settings, settings_initial):
            fail("daemon settings changed while applying config.toml; retry")
        if new_settings != old_settings:
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
        # Roll back only the fields this transaction wrote. Do not discard backups.
        if not unchanged(conf, config_initial):
            if config_existed:
                atomic_write(conf, old_config, config_mode)
            else:
                conf.unlink(missing_ok=True)
        if not unchanged(settings, settings_initial):
            if settings_existed:
                atomic_write(settings, old_settings, settings_mode)
            else:
                settings.unlink(missing_ok=True)
        raise

    print("Applied background optimization." if optimize else "Restored native background configuration.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["status", "optimize", "native", "check"])
    parser.add_argument("--target", choices=["optimize", "native"])
    parser.add_argument("--yes", action="store_true", help="explicitly resolve managed-key conflicts")
    parser.add_argument("--codex-home", required=True)
    parser.add_argument("--config-dir", required=True)
    args = parser.parse_args()
    try:
        if args.action in ("status", "check"):
            if args.action == "check" and not args.target:
                fail("check requires --target optimize|native")
            return status(args)
        return apply(args, optimize=args.action == "optimize")
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"background policy error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
