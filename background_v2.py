#!/usr/bin/env python3
"""Live Codex background state reconciliation. Requires vendored tomlkit."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import select
import stat
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent / 'vendor'))
import tomlkit

import background as legacy

TOOL_VERSION = "2.2.0"
TOML_KEYS = ("check_for_update_on_startup", "features.daemon_auto_start")
JSON_KEYS = ("remoteControlEnabled", "updater.autoUpdateEnabled")
COMMENTS = {
    "check_for_update_on_startup": "# codex-tool: Disable startup update checks; update through codex-tool.",
    "features.daemon_auto_start": "# codex-tool: Prevent automatic shared daemon startup.",
}
ALL_KEYS = TOML_KEYS + JSON_KEYS
HEADER = re.compile(r"^\s*\[(?:\[)?[^\r\n]+\](?:\])?\s*(?:#.*)?$")
ASSIGN = re.compile(r"^(\s*)([A-Za-z_][\w.-]*)(\s*)=(\s*)(.*)$")

class BackgroundError(Exception):
    pass

def fail(message):
    raise BackgroundError(message)

def paths(args):
    return (Path(args.codex_home) / "config.toml",
            Path(args.codex_home) / "app-server-daemon" / "settings.json",
            Path(args.config_dir) / "background")

def checked_file(path):
    if path.is_symlink():
        fail(f"refusing symlink config: {path}")
    if path.exists() and (not path.is_file() or path.stat().st_uid != os.getuid()):
        fail(f"unsafe file ownership/type: {path}")
    return legacy.load_text(path)

def parse_toml(text):
    try:
        return tomlkit.parse(text)
    except Exception as exc:
        fail(f"invalid TOML: {exc}")

def as_plain(item):
    return item.unwrap() if hasattr(item, "unwrap") else item

def toml_field(doc, key):
    node = doc
    for part in key.split("."):
        if part not in node:
            return {"present": False, "value": None}
        node = node[part]
    return {"present": True, "value": as_plain(node)}

def json_field(tree, key):
    node = tree
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return {"present": False, "value": None}
        node = node[part]
    return {"present": True, "value": node}

def json_tree(text):
    try:
        value = json.loads(text) if text.strip() else {}
    except ValueError as exc:
        fail(f"invalid daemon settings JSON: {exc}")
    if not isinstance(value, dict):
        fail("daemon settings root must be an object")
    return value

def observe_files(config, settings):
    doc = parse_toml(config)
    other = json_tree(settings)
    return {**{key: toml_field(doc, key) for key in TOML_KEYS},
            **{key: json_field(other, key) for key in JSON_KEYS}}

def desired_optimized():
    return {k: {"present": True, "value": False} for k in ALL_KEYS}

def metadata_originals(manifest):
    if not manifest:
        return None
    try:
        t, j = legacy.original_snapshots(manifest)
    except (ValueError, TypeError, KeyError) as exc:
        fail(f"corrupt original metadata: {exc}")
    return {**t, **j}

def manifest_read(file):
    if file.is_symlink():
        fail("refusing symlink manifest")
    if not file.exists():
        return None
    if not file.is_file() or file.stat().st_uid != os.getuid():
        fail("unsafe manifest")
    try:
        obj = json.loads(file.read_text("utf-8"))
    except (ValueError, OSError) as exc:
        fail(f"invalid manifest: {exc}")
    if obj.get("schema") not in (1, 2, 3):
        fail("unsupported background manifest schema")
    originals = metadata_originals(obj)
    if set(originals) != set(ALL_KEYS):
        fail("background manifest lacks original keys")
    return obj

def version_hash(path):
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()

class CodexAPI:
    """Isolated, timeout-bounded App-server stdio JSON-RPC client; never starts a daemon."""
    def __init__(self, binary, timeout=7):
        self.binary = binary
        self.timeout = timeout
        self.proc = None
        self.sequence = 0

    def __enter__(self):
        self.proc = subprocess.Popen(
            [str(self.binary), "app-server", "--listen", "stdio://"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            close_fds=True, start_new_session=True,
        )
        try:
            self.request("initialize", {"clientInfo": {"name": "codex-tool", "version": TOOL_VERSION},
                                        "capabilities": {"experimentalApi": False}})
            self.send({"jsonrpc": "2.0", "method": "initialized", "params": {}})
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.proc is None:
            return
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=2)
        self.proc.stdin.close()
        self.proc.stdout.close()

    def send(self, payload):
        data = json.dumps(payload, separators=(",", ":")).encode() + b"\n"
        self.proc.stdin.write(data)
        self.proc.stdin.flush()

    def request(self, method, params):
        self.sequence += 1
        ident = self.sequence
        self.send({"jsonrpc": "2.0", "id": ident, "method": method, "params": params})
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if self.proc.poll() is not None:
                fail(f"Codex app-server terminated during {method}")
            ready, _, _ = select.select([self.proc.stdout], [], [], max(0, remaining))
            if not ready:
                break
            line = self.proc.stdout.readline()
            if not line:
                fail(f"Codex app-server closed stdout during {method}")
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("id") != ident:
                continue
            if "error" in msg:
                fail(f"Codex API {method}: {msg['error']}")
            return msg.get("result", {})
        fail(f"Codex API {method} timeout")

    def read(self, cwd=None):
        response = self.request("config/read", {"includeLayers": True, "cwd": cwd})
        requirements = self.request("configRequirements/read", {})
        return {"read": response, "requirements": requirements}

    def user_version(self, response, config_path):
        layers = response.get("layers") or []
        for layer in layers:
            name = layer.get("name") or {}
            if name.get("type") == "user" and (not name.get("profile")):
                file = name.get("file")
                if file and Path(file).resolve() == config_path.resolve():
                    return layer.get("version")
        return None

    def write(self, edits, version):
        if version is None:
            fail("Codex API did not provide the user config layer version")
        response = self.request("config/batchWrite", {
            "edits": [{"keyPath": key, "value": value, "mergeStrategy": "replace"}
                      for key, value in edits.items()],
            "expectedVersion": version, "reloadUserConfig": False,
        })
        if response.get("status") != "ok":
            fail(f"Codex API write did not become effective: {response}")
        return response

def api_probe(args):
    binary = getattr(args, "codex_bin", None)
    if not binary or not Path(binary).is_file() or not os.access(binary, os.X_OK):
        return None, "no Codex binary available for API read"
    try:
        with CodexAPI(binary) as api:
            return api.read(getattr(args, "cwd", None)), None
    except (OSError, BackgroundError, ValueError) as exc:
        return None, str(exc)

def effective_key(response, key):
    if response is None:
        return None
    cur = response.get("read", {}).get("config", {})
    for name in key.split("."):
        if not isinstance(cur, dict) or name not in cur:
            return None
        cur = cur[name]
    return cur

def origin_key(response, key):
    if response is None:
        return None
    return (response.get("read", {}).get("origins") or {}).get(key)

def collect(args):
    conf, settings, policy = paths(args)
    cfg_exists, cfg, cfg_mode = checked_file(conf)
    settings_exists, settings_text, settings_mode = checked_file(settings)
    manifest = manifest_read(policy / "manifest.json")
    current = observe_files(cfg, settings_text)
    api, api_error = (None, "skipped by request") if args.no_api else api_probe(args)
    target = desired_optimized()
    drift = [dict(key=k, current=current[k], target=target[k]) for k in ALL_KEYS if current[k] != target[k]]
    toml_matches = all(current[k] == target[k] for k in TOML_KEYS)
    daemon_matches = all(current[k] == target[k] for k in JSON_KEYS)
    effective = {}
    overrides = []
    for k in TOML_KEYS:
        value = effective_key(api, k)
        effective[k] = {"value": value, "origin": origin_key(api, k)}
        if api is not None and value is not None and value is not False:
            overrides.append(k)
    disabled = [current[k]["present"] and current[k]["value"] is False for k in ALL_KEYS]
    # File-state classification must never depend on persisted recovery metadata.
    config_state = ("optimized" if toml_matches and daemon_matches else
                    "drifted" if any(disabled) else "native-compatible")
    if overrides:
        config_state = "overridden"
    if api is None and not args.no_api:
        config_state = "unknown" if toml_matches and daemon_matches else config_state
    return {"config": config_state, "configuration": current, "effective": effective,
            "drift": drift, "overridden": overrides, "api_ok": api is not None,
            "api_error": api_error, "layers": [{"name": row.get("name"), "version": row.get("version"), "disabledReason": row.get("disabledReason")} for row in ((api or {}).get("read", {}).get("layers") or [])],
            "manifest_schema": manifest.get("schema") if manifest else None,
            "manifest": manifest, "api": api, "file": (cfg_exists, cfg, cfg_mode),
            "settings_file": (settings_exists, settings_text, settings_mode),
            "config_path": conf, "settings_path": settings, "policy_path": policy}

def canonicalize(text):
    """Canonical root/table/assignment spacing, outside TOML multiline strings."""
    lines = text.replace("\r\n", "\n").splitlines()
    result = []
    triple = None
    for row in lines:
        trimmed = row.strip()
        active = triple is not None
        if not active and HEADER.match(trimmed):
            while result and not result[-1].strip():
                result.pop()
            if result:
                result.append("")
            result.append(trimmed)
        elif not active:
            m = ASSIGN.match(row)
            if m and not trimmed.startswith("#"):
                result.append(f"{m.group(2)} = {m.group(5)}")
            else:
                result.append(row.rstrip())
        else:
            result.append(row)
        # Toggle only on unescaped triple quote delimiters, preserving literal contents.
        # Semantic comparison below catches any ambiguous legal TOML construct.
        for symbol in ('"""', "'''"):
            if triple is None and symbol in row:
                if row.count(symbol) % 2:
                    triple = symbol
                break
            if triple == symbol and row.count(symbol) % 2:
                triple = None
                break
    return "\n".join(result).rstrip("\n") + ("\n" if result else "")

def annotate(text, desired):
    """Attach explanatory comments to managed lines, retaining all user comments."""
    lines = [line for line in text.splitlines() if line.strip() not in COMMENTS.values()]
    section = ""
    out = []
    for row in lines:
        if HEADER.match(row.strip()):
            section = row.strip().strip("[]").split("#", 1)[0].strip()
        m = ASSIGN.match(row)
        key = m.group(2) if m else None
        full = f"{section}.{key}" if section and key else key
        if full in COMMENTS and desired.get(full, {}).get("present"):
            out.append(COMMENTS[full])
        out.append(row)
    return "\n".join(out).rstrip("\n") + ("\n" if out else "")

def edit_toml(text, changes, annotate_managed):
    doc = parse_toml(text)
    original = as_plain(doc)
    for key, meta in changes.items():
        if key not in TOML_KEYS:
            continue
        parts = key.split(".")
        target = doc
        for segment in parts[:-1]:
            if segment not in target:
                target.add(segment, tomlkit.table())
            target = target[segment]
            if not hasattr(target, "__setitem__"):
                fail(f"TOML key cannot contain a nested field: {key}")
        name = parts[-1]
        if meta["present"]:
            if not isinstance(meta["value"], bool):
                fail(f"unsupported managed boolean value: {key}")
            target[name] = meta["value"]
        elif name in target:
            del target[name]
    if ("features" not in original and "features" in doc and
            not doc["features"] and
            not changes.get("features.daemon_auto_start", {}).get("present", False)):
        del doc["features"]
    raw = tomlkit.dumps(doc)
    output = canonicalize(raw)
    if annotate_managed:
        output = annotate(output, changes)
    else:
        output = "\n".join(line for line in output.splitlines()
                           if line.strip() not in COMMENTS.values()).rstrip("\n") + "\n" if output else ""
    updated = as_plain(parse_toml(output))
    expected = copy.deepcopy(original)
    for key, meta in changes.items():
        segments = key.split(".")
        parent = expected
        for part in segments[:-1]:
            parent = parent.setdefault(part, {})
        if meta["present"]:
            parent[segments[-1]] = meta["value"]
        else:
            parent.pop(segments[-1], None)
    if updated != expected:
        fail("TOML formatter changed unrelated values; refusing to write")
    return output

def edit_json(text, changes):
    tree = json_tree(text)
    original = copy.deepcopy(tree)
    for key, meta in changes.items():
        if key not in JSON_KEYS:
            continue
        parts = key.split(".")
        node = tree
        for part in parts[:-1]:
            if not meta["present"] and part not in node:
                break
            if part not in node:
                node[part] = {}
            if not isinstance(node[part], dict):
                fail(f"JSON parent is not an object: {key}")
            node = node[part]
        else:
            if meta["present"]:
                node[parts[-1]] = meta["value"]
            else:
                node.pop(parts[-1], None)
    # Remove an empty parent introduced solely by the optimizer, not a user-owned table.
    for key, meta in changes.items():
        if key in JSON_KEYS and not meta["present"] and "." in key:
            parent = key.split(".")[0]
            if parent not in original and tree.get(parent) == {}:
                tree.pop(parent)
    if original == tree:
        return text
    return json.dumps(tree, indent=2, ensure_ascii=False) + "\n"

def original_manifest(state):
    _, cfg, cfg_mode = state["file"]
    _, js, js_mode = state["settings_file"]
    first = observe_files(cfg, js)
    return {
        "schema": 3, "mode": "optimized", "applied": legacy.managed_applied(),
        "config_existed": state["file"][0], "settings_existed": state["settings_file"][0],
        "config_mode": cfg_mode, "settings_mode": js_mode,
        "features_header_existed": "features" in parse_toml(cfg),
        "toml_originals": {k: {"present": first[k]["present"], "line": (
            f'{k.split(".")[-1]} = {str(first[k]["value"]).lower()}\n' if first[k]["present"] else None)}
            for k in TOML_KEYS},
        "json_originals": {k: first[k] for k in JSON_KEYS},
    }

def plan(state, target):
    manifest = state["manifest"]
    if target == "native":
        if manifest is None:
            return {}, False
        desired = metadata_originals(manifest)
    else:
        desired = desired_optimized()
    changes = {k: v for k, v in desired.items() if v != state["configuration"][k]}
    conflict = bool(changes) and manifest is not None and target == "optimize"
    if target == "native" and changes:
        applied = desired_optimized()
        conflict = any(state["configuration"][k] not in (desired[k], applied[k]) for k in changes)
    return changes, conflict

def atomic_write(path, content, mode):
    legacy.atomic_write(path, content, mode)

def apply(args):
    state = collect(args)
    target = args.action
    changes, conflict = plan(state, target)
    if conflict and not args.yes:
        fail("managed configuration drift requires confirmation; review status and rerun with --yes")
    if target == "native" and not state["manifest"]:
        print("Native restoration: no managed original backup is available.")
        return 0
    doc_target = (desired_optimized() if target == "optimize"
                  else metadata_originals(state["manifest"]))
    conf_path, settings_path, policy = paths(args)
    old_cfg = state["file"][1]
    old_js = state["settings_file"][1]
    new_cfg = edit_toml(old_cfg, {k: doc_target[k] for k in TOML_KEYS}, target == "optimize")
    if target == "native" and not state["manifest"].get("features_header_existed", True):
        doc = parse_toml(new_cfg)
        if "features" in doc and not doc["features"]:
            del doc["features"]
            new_cfg = canonicalize(tomlkit.dumps(doc))
    new_js = edit_json(old_js, {k: doc_target[k] for k in JSON_KEYS})
    if target == "native":
        # Only prune empty JSON parents absent in the first-optimization snapshot.
        source_backup = policy / "backup" / "daemon-settings.json"
        if source_backup.exists() and not source_backup.is_symlink():
            backup_tree = json_tree(source_backup.read_text("utf-8"))
            restored_tree = json_tree(new_js)
            if "updater" not in backup_tree and restored_tree.get("updater") == {}:
                restored_tree.pop("updater")
                new_js = json.dumps(restored_tree, indent=2, ensure_ascii=False) + "\n"
    needs_cfg = new_cfg != old_cfg
    needs_js = new_js != old_js
    if args.dry_run:
        print(json.dumps({"target": target, "changes": changes, "format_config": needs_cfg,
                          "format_settings": needs_js, "requires_confirmation": conflict}, ensure_ascii=False))
        return 0
    if args.no_api and not args.allow_direct_write:
        fail("API bypass forbidden outside explicit direct-write recovery")
    if needs_cfg and not args.allow_direct_write:
        if state["api"] is None:
            fail("Codex config API is unavailable: " + str(state["api_error"]))
        if state["overridden"]:
            fail("Codex config is overridden by a higher-priority layer: " + ", ".join(state["overridden"]))
    if any(checked_file(p) != base for p, base in ((conf_path, state["file"]), (settings_path, state["settings_file"]))):
        fail("config changed while preparing transaction; retry")
    backup_path = policy / "backup"
    manifest = state["manifest"] or original_manifest(state)
    if manifest.get("schema") != 3:
        manifest = {**manifest, "schema": 3}
    legacy.private_dir(policy)
    legacy.private_dir(backup_path)
    # Transaction journal contains hashes only, not user configuration or secrets.
    pending = policy / "pending.json"
    if pending.exists():
        fail("incomplete previous background transaction; recovery required")
    journal = {"target": target, "config_sha256": hashlib.sha256(old_cfg.encode()).hexdigest(),
               "settings_sha256": hashlib.sha256(old_js.encode()).hexdigest(),
               "version": TOOL_VERSION}
    atomic_write(pending, json.dumps(journal, indent=2) + "\n", 0o600)
    wrote_config = False
    wrote_settings = False
    try:
        if target == "optimize" and state["manifest"] is None:
            atomic_write(backup_path / "config.toml", old_cfg, 0o600)
            atomic_write(backup_path / "daemon-settings.json", old_js, 0o600)
        if needs_cfg:
            if not args.allow_direct_write:
                with CodexAPI(args.codex_bin) as api:
                    response = api.read(args.cwd)
                    version = api.user_version(response["read"], conf_path)
                    edits = {k: (doc_target[k]["value"] if doc_target[k]["present"] else None)
                             for k in TOML_KEYS if state["configuration"][k] != doc_target[k]}
                    if edits:
                        api.write(edits, version)
                # API writing is the authoritative field mutation. Reread it before formatting.
                _, intermediate, _ = checked_file(conf_path)
                after_api = observe_files(intermediate, old_js)
                if any(after_api[k] != doc_target[k] for k in TOML_KEYS):
                    fail("Codex API write did not produce required user config values")
                new_cfg = edit_toml(intermediate, {k: doc_target[k] for k in TOML_KEYS},
                                    target == "optimize")
                if checked_file(settings_path) != state["settings_file"]:
                    fail("daemon settings changed concurrently")
                if checked_file(conf_path)[1] != intermediate:
                    fail("Codex config changed after API write, before formatting; retry")
                wrote_config = intermediate != old_cfg
                atomic_write(conf_path, new_cfg, state["file"][2])
            else:
                atomic_write(conf_path, new_cfg, state["file"][2])
                wrote_config = True
        if needs_js:
            if checked_file(settings_path) != state["settings_file"]:
                fail("daemon settings changed concurrently")
            atomic_write(settings_path, new_js, state["settings_file"][2])
            wrote_settings = True
        current = observe_files(checked_file(conf_path)[1], checked_file(settings_path)[1])
        if any(current[k] != doc_target[k] for k in ALL_KEYS):
            fail("post-write verification failed")
        if target == "optimize":
            atomic_write(policy / "manifest.json", json.dumps(manifest, indent=2) + "\n", 0o600)
        else:
            (policy / "manifest.json").unlink(missing_ok=True)
            # Original snapshots are no longer required after native restoration.
            for path in (backup_path / "config.toml", backup_path / "daemon-settings.json"):
                path.unlink(missing_ok=True)
            # Remove config created solely by codex-tool when no unrelated data remains.
            if not manifest.get("config_existed") and not parse_toml(checked_file(conf_path)[1]):
                conf_path.unlink(missing_ok=True)
            if not manifest.get("settings_existed") and not json_tree(checked_file(settings_path)[1]):
                settings_path.unlink(missing_ok=True)
        pending.unlink(missing_ok=True)
    except Exception:
        # Recover only if current bytes equal our own changes; preserve later external edits.
        if wrote_settings and checked_file(settings_path)[1] == new_js:
            atomic_write(settings_path, old_js, state["settings_file"][2])
        if (wrote_config or needs_cfg) and conf_path.exists():
            current_text = checked_file(conf_path)[1]
            if current_text == new_cfg or current_text == old_cfg or (
                observe_files(current_text, old_js) and
                all(observe_files(current_text, old_js)[k] == doc_target[k] for k in TOML_KEYS)):
                if state["file"][0]:
                    atomic_write(conf_path, old_cfg, state["file"][2])
                else:
                    conf_path.unlink(missing_ok=True)
        # Keep pending journal if rollback could not be established automatically.
        if checked_file(conf_path)[1] == old_cfg and checked_file(settings_path)[1] == old_js:
            pending.unlink(missing_ok=True)
        raise
    print(f"Background {target} configuration applied and verified.")
    return 0

def public_state(state):
    return {k: v for k, v in state.items() if k not in (
        "manifest", "api", "file", "settings_file", "config_path", "settings_path", "policy_path")}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("status", "check", "optimize", "native"))
    parser.add_argument("--target", choices=("optimize", "native"))
    parser.add_argument("--codex-home", required=True)
    parser.add_argument("--config-dir", required=True)
    parser.add_argument("--codex-bin")
    parser.add_argument("--cwd")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-api", action="store_true")
    parser.add_argument("--allow-direct-write", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if args.action == "status":
            print(json.dumps(public_state(collect(args)), ensure_ascii=False))
            return 0
        if args.action == "check":
            if not args.target:
                fail("check requires --target")
            state = collect(args)
            edits, conflict = plan(state, args.target)
            print(json.dumps({"target": args.target, "mode": state["config"],
                              "changes": [{"key": k, "current": state["configuration"][k],
                                           "target": v} for k, v in edits.items()],
                              "confirmation_required": conflict,
                              "manifest_schema": state["manifest_schema"]}, ensure_ascii=False))
            return 0
        return apply(args)
    except (BackgroundError, OSError, ValueError, TypeError, KeyError) as exc:
        print(f"background reconciliation error: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
