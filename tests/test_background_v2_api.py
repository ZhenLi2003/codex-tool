"""Mock the Codex app-server JSON-RPC protocol without starting a real daemon."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "background_v2.py"

MOCK = r'''#!/usr/bin/env python3
import hashlib
import json
import sys
from pathlib import Path
import tomlkit

config = Path(__CONFIG__)
for line in sys.stdin:
    try:
        req = json.loads(line)
        ident = req.get("id")
        if ident is None:
            continue
        method, params = req.get("method"), req.get("params") or {}
        current = config.read_text() if config.exists() else ""
        version = hashlib.sha256(current.encode()).hexdigest()
        if method == "initialize":
            result = {}
        elif method == "config/read":
            tree = tomlkit.parse(current).unwrap()
            result = {"config": tree, "origins": {},
                      "layers": [{"name": {"type": "user", "file": str(config), "profile": None},
                                  "version": version, "config": tree}]}
        elif method == "configRequirements/read":
            result = {}
        elif method == "config/batchWrite":
            if params.get("expectedVersion") != version:
                print(json.dumps({"jsonrpc":"2.0", "id": ident,
                     "error":{"code":-32000,"message":"ConfigVersionConflict"}}),flush=True)
                continue
            tree = tomlkit.parse(current)
            for change in params["edits"]:
                key_path = change["keyPath"]
                segments = key_path.split(".")
                obj = tree
                for part in segments[:-1]:
                    if part not in obj:
                        obj.add(part,tomlkit.table())
                    obj = obj[part]
                if change["value"] is None:
                    if segments[-1] in obj:
                        del obj[segments[-1]]
                else:
                    obj[segments[-1]] = change["value"]
            config.write_text(tomlkit.dumps(tree))
            version = hashlib.sha256(config.read_bytes()).hexdigest()
            result = {"status": "ok", "version": version, "filePath": str(config)}
        else:
            print(json.dumps({"jsonrpc":"2.0", "id": ident,
                  "error":{"code":-32601,"message":"method not found"}}),flush=True)
            continue
        print(json.dumps({"jsonrpc":"2.0", "id": ident, "result":result}),flush=True)
    except Exception as exc:
        print(json.dumps({"jsonrpc":"2.0", "id": req.get("id"),
              "error":{"code":-32603,"message":str(exc)}}),flush=True)
'''

class CodexApiRoundTripTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name) / "codex-home"
        self.home.mkdir()
        self.config = self.home / "config.toml"
        self.settings = self.home / "app-server-daemon" / "settings.json"
        self.settings.parent.mkdir()
        self.state = Path(temp.name) / "state"
        self.binary = Path(temp.name) / "codex-mock"
        self.binary.write_text(MOCK.replace("__CONFIG__", repr(str(self.config))))
        self.binary.chmod(0o755)

    def call(self, action, *args, success=True):
        command = [sys.executable, str(ENGINE), action,
                   "--codex-home", str(self.home),
                   "--config-dir", str(self.state),
                   "--codex-bin", str(self.binary), *args]
        env = dict(os.environ, PYTHONPATH=str(ROOT / "vendor"))
        completed = subprocess.run(command, capture_output=True, text=True, timeout=25, env=env)
        if success:
            self.assertEqual(completed.returncode, 0, completed.stderr)
        else:
            self.assertNotEqual(completed.returncode, 0)
        return completed

    def test_official_api_write_then_native_roundtrip(self):
        self.config.write_text('model="gpt-6"\n[features]\nmulti_agent=true\n')
        self.call("optimize")
        result = json.loads(self.call("status").stdout)
        self.assertEqual(result["config"], "optimized")
        self.assertTrue(result["api_ok"])
        self.assertFalse(result["effective"]["features.daemon_auto_start"]["value"])
        self.assertIn('# codex-tool:', self.config.read_text())
        self.call("native")
        restored = self.config.read_text()
        self.assertNotIn("daemon_auto_start",restored)
        self.assertNotIn("check_for_update_on_startup",restored)
        self.assertIn('model = "gpt-6"',restored)

    def test_api_rejects_invalid_read_write(self):
        # Wrong file permission / symlink is rejected before any API write.
        self.config.symlink_to(self.home / "somewhere")
        self.call("optimize", success=False)
        self.assertFalse((self.state / "background" / "manifest.json").exists())

if __name__ == "__main__":
    unittest.main()
