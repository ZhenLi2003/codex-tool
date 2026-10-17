#!/usr/bin/env python3
"""End-to-end local configuration reconciliation without a live Codex service."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "background_v2.py"

class EndToEndTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.home = self.base / "codex-home"
        self.home.mkdir()
        self.settings = self.home / "app-server-daemon" / "settings.json"
        self.settings.parent.mkdir()
        self.toml = self.home / "config.toml"
        self.manifest = self.base / "config" / "background" / "manifest.json"

    def invoke(self, command, *more, success=True):
        p = subprocess.run([sys.executable, str(ENGINE), command,
                            "--codex-home", str(self.home),
                            "--config-dir", str(self.base / "config"),
                            "--no-api", *more], capture_output=True, text=True)
        if success:
            self.assertEqual(p.returncode, 0, p.stderr)
        else:
            self.assertNotEqual(p.returncode, 0, p.stdout)
        return p

    def test_first_optimize_then_native_preserves_unrelated(self):
        self.toml.write_text('model="gpt-6"\n\n[features]\nmulti_agent=true\n')
        self.settings.write_text('{"remoteControlEnabled": true, "updater": {"autoUpdateEnabled": true}, "other": 7}')
        self.invoke("optimize", "--allow-direct-write")
        self.assertEqual(json.loads(self.invoke("status").stdout)["config"], "optimized")
        self.assertEqual(json.loads(self.settings.read_text())["other"], 7)
        self.assertEqual(json.loads(self.manifest.read_text())["schema"], 3)
        updated = self.toml.read_text().replace('model = "gpt-6"', 'model = "gpt-6-mini"')
        self.toml.write_text(updated)
        self.invoke("native", "--allow-direct-write")
        self.assertIn('model = "gpt-6-mini"', self.toml.read_text())
        self.assertIn('multi_agent = true', self.toml.read_text())
        self.assertNotIn('daemon_auto_start', self.toml.read_text())
        self.assertNotIn('check_for_update_on_startup', self.toml.read_text())
        self.assertIs(json.loads(self.settings.read_text())["remoteControlEnabled"], True)
        self.assertFalse(self.manifest.exists())

    def test_missing_files_roundtrip_to_absence(self):
        self.invoke("optimize", "--allow-direct-write")
        self.assertTrue(self.toml.exists())
        self.invoke("native", "--allow-direct-write")
        self.assertFalse(self.toml.exists())
        self.assertFalse(self.settings.exists())

    def test_manual_drift_requires_confirmation(self):
        self.invoke("optimize", "--allow-direct-write")
        self.toml.write_text(self.toml.read_text().replace(
            "daemon_auto_start = false", "daemon_auto_start = true"))
        state = json.loads(self.invoke("status").stdout)
        self.assertEqual(state["config"], "drifted")
        self.invoke("optimize", "--allow-direct-write", success=False)
        self.invoke("optimize", "--allow-direct-write", "--yes")
        self.assertEqual(json.loads(self.invoke("status").stdout)["config"], "optimized")

    def test_invalid_toml_does_not_write(self):
        broken = '[features]\ndaemon_auto_start=true\ndaemon_auto_start=false\n'
        self.toml.write_text(broken)
        self.invoke("optimize", "--allow-direct-write", success=False)
        self.assertEqual(self.toml.read_text(), broken)
        self.assertFalse(self.manifest.exists())

    def test_api_write_required_by_default(self):
        self.invoke("optimize", success=False)
        self.assertFalse(self.manifest.exists())

    def test_dry_run_is_read_only(self):
        self.toml.write_text('model="gpt-6"\n')
        initial = self.toml.read_bytes()
        info = json.loads(self.invoke("optimize", "--dry-run").stdout)
        self.assertTrue(info["format_config"])
        self.assertEqual(self.toml.read_bytes(), initial)

if __name__ == "__main__":
    unittest.main()
