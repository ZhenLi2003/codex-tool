#!/usr/bin/env python3
"""Regression tests for manual config edits and legacy background backup migration."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest

HELPER = Path(__file__).resolve().parents[1] / "background.py"


class BackgroundReconciliationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.home = self.root / ".codex"
        self.conf = self.home / "config.toml"
        self.settings = self.home / "app-server-daemon" / "settings.json"
        self.state_dir = self.root / "config" / "codex-tool" / "background"
        self.manifest = self.state_dir / "manifest.json"

    def call(self, action, *args, ok=True):
        result = subprocess.run(
            [sys.executable, str(HELPER), action, *args,
             "--codex-home", str(self.home),
             "--config-dir", str(self.state_dir.parent)],
            capture_output=True, text=True,
        )
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def state(self):
        return json.loads(self.call("status").stdout)

    def test_optimize_repairs_manual_edits_without_losing_original_backup(self):
        self.conf.parent.mkdir(parents=True)
        self.conf.write_text('model = "gpt-6"\n[features]\ndaemon_auto_start = true # managed\n')
        self.call("optimize")
        backup = (self.state_dir / "backup" / "config.toml").read_bytes()

        self.conf.write_text(self.conf.read_text().replace(
            'daemon_auto_start = false', 'daemon_auto_start = true'
        ).replace('model = "gpt-6"', 'model = "gpt-6-mini"'))
        self.assertEqual(self.state()["effective"], "modified")
        self.assertIn("daemon_auto_start", self.call("optimize", ok=False).stderr)
        plan = json.loads(self.call("check", "--target", "optimize").stdout)
        self.assertTrue(plan["confirmation_required"])
        self.call("optimize", "--yes")
        self.assertEqual(self.state()["effective"], "optimized")
        self.assertEqual((self.state_dir / "backup" / "config.toml").read_bytes(), backup)
        self.call("native")
        restored = self.conf.read_text()
        self.assertIn('model = "gpt-6-mini"', restored)
        self.assertIn("daemon_auto_start = true", restored)
        self.assertNotIn("check_for_update_on_startup = false", restored)

    def test_native_accepts_field_already_restored_by_hand(self):
        self.conf.parent.mkdir(parents=True)
        self.conf.write_text('[features]\ndaemon_auto_start = true\n')
        self.call("optimize")
        self.conf.write_text(self.conf.read_text().replace(
            'daemon_auto_start = false', 'daemon_auto_start = true'))
        plan = json.loads(self.call("check", "--target", "native").stdout)
        self.assertFalse(plan["confirmation_required"])
        self.call("native")
        self.assertFalse(self.manifest.exists())
        self.assertIn("daemon_auto_start = true", self.conf.read_text())

    def test_optimizing_absent_key_drift_requires_confirmation(self):
        self.call("optimize")
        self.conf.write_text(self.conf.read_text().replace('daemon_auto_start = false\n', ''))
        self.assertEqual(self.state()["effective"], "modified")
        self.call("optimize", ok=False)
        self.call("optimize", "--yes")
        self.assertEqual(self.state()["effective"], "optimized")
        self.call("native")
        self.assertFalse(self.conf.exists())
        self.assertFalse(self.settings.exists())

    def test_deleted_native_original_key_needs_confirmation(self):
        self.conf.parent.mkdir(parents=True)
        self.conf.write_text('[features]\ndaemon_auto_start = true\n')
        self.call("optimize")
        self.conf.write_text(self.conf.read_text().replace('daemon_auto_start = false\n', ''))
        plan = json.loads(self.call("check", "--target", "native").stdout)
        self.assertTrue(plan["confirmation_required"])
        self.call("native", ok=False)
        self.call("native", "--yes")
        self.assertIn("daemon_auto_start = true", self.conf.read_text())

    def test_settings_manual_restore_and_unrelated_edits(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(json.dumps({
            "remoteControlEnabled": True,
            "updater": {"autoUpdateEnabled": True, "updateIntervalMinutes": 60},
            "shutdownGraceSeconds": 45,
        }))
        self.call("optimize")
        data = json.loads(self.settings.read_text())
        data["remoteControlEnabled"] = True
        data["updater"]["autoUpdateEnabled"] = True
        data["shutdownGraceSeconds"] = 15
        self.settings.write_text(json.dumps(data))
        self.call("native")
        data = json.loads(self.settings.read_text())
        self.assertIs(data["remoteControlEnabled"], True)
        self.assertIs(data["updater"]["autoUpdateEnabled"], True)
        self.assertEqual(data["shutdownGraceSeconds"], 15)

    def test_json_third_state_requires_explicit_confirmation(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text('{"remoteControlEnabled":true}')
        self.call("optimize")
        data = json.loads(self.settings.read_text())
        data["remoteControlEnabled"] = None
        self.settings.write_text(json.dumps(data))
        self.call("native", ok=False)
        self.assertTrue(self.manifest.exists())
        self.call("native", "--yes")
        self.assertIs(json.loads(self.settings.read_text())["remoteControlEnabled"], True)

    def test_schema_v1_migration_does_not_rewrite_original_backups(self):
        self.call("optimize")
        first_backup = (self.state_dir / "backup" / "config.toml").read_bytes()
        data = json.loads(self.manifest.read_text())
        data["schema"] = 1
        data.pop("mode", None)
        data.pop("applied", None)
        self.manifest.write_text(json.dumps(data))
        self.assertEqual(self.state()["manifest_schema"], 1)
        self.call("optimize")
        data = json.loads(self.manifest.read_text())
        self.assertEqual(data["schema"], 2)
        self.assertEqual(data["applied"]["toml"]["features.daemon_auto_start"]["value"], False)
        self.assertEqual((self.state_dir / "backup" / "config.toml").read_bytes(), first_backup)
        self.call("native")
        self.assertFalse(self.manifest.exists())

    def test_invalid_toml_is_rejected_with_backup_unchanged(self):
        self.call("optimize")
        backup = (self.state_dir / "backup" / "config.toml").read_bytes()
        self.conf.write_text('[features]\ndaemon_auto_start = true\ndaemon_auto_start = false\n')
        self.call("optimize", "--yes", ok=False)
        self.assertEqual((self.state_dir / "backup" / "config.toml").read_bytes(), backup)

    def test_repeated_optimize_preserves_json_formatting_and_legacy_backup(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text('{"remoteControlEnabled": true, "updater": {"autoUpdateEnabled": true}}\n')
        self.call("optimize")
        self.settings.write_text(json.dumps(json.loads(self.settings.read_text()), separators=(",", ":")) + "\n")
        expected = self.settings.read_bytes()
        self.call("optimize")
        self.assertEqual(self.settings.read_bytes(), expected)

    def test_toml_section_spacing_and_managed_comments(self):
        self.conf.parent.mkdir(parents=True)
        original = (
            'model = "gpt-6"\n'
            '\n'
            '[features]\n'
            'multi_agent = true\n'
            '\n'
            '[mcp_servers.example]\n'
            'enabled = false\n'
        )
        self.conf.write_text(original, encoding="utf-8")
        self.call("optimize")
        optimized = self.conf.read_text()
        self.assertEqual(optimized.count("[features]"), 1)
        self.assertIn("\n\n[features]\n", optimized)
        self.assertIn("\n\n[mcp_servers.example]\n", optimized)
        self.assertEqual(optimized.count("# codex-tool: Prevent ordinary Codex sessions"), 1)
        self.assertEqual(optimized.count("# codex-tool: Disable automatic CLI update checks"), 1)
        self.call("optimize")
        self.assertEqual(self.conf.read_text(), optimized)
        self.call("native")
        self.assertEqual(self.conf.read_text(), original)

    def test_comments_follow_reconciliation_and_disappear_on_native(self):
        self.conf.parent.mkdir(parents=True)
        self.conf.write_text("[features]\n# user comment\ndaemon_auto_start = true # keep existing\n")
        self.call("optimize")
        edited = self.conf.read_text().replace("daemon_auto_start = false", "daemon_auto_start = true")
        self.conf.write_text(edited)
        self.call("optimize", "--yes")
        self.assertEqual(self.conf.read_text().count("# codex-tool: Prevent ordinary Codex sessions"), 1)
        self.call("native")
        self.assertNotIn("# codex-tool:", self.conf.read_text())
        self.assertIn("# user comment", self.conf.read_text())

    def test_original_toml_without_final_newline(self):
        self.conf.parent.mkdir(parents=True)
        self.conf.write_text('model = "gpt-6"', encoding="utf-8")
        self.call("optimize")
        self.assertEqual(self.state()["effective"], "optimized")
        self.call("native")
        self.assertEqual(self.conf.read_text(), 'model = "gpt-6"')

    def test_native_of_original_false_is_idempotent(self):
        self.conf.parent.mkdir(parents=True)
        self.conf.write_text('[features]\ndaemon_auto_start = false\n')
        self.call("optimize")
        self.call("native")
        self.assertIn("daemon_auto_start = false", self.conf.read_text())


if __name__ == "__main__":
    unittest.main()
