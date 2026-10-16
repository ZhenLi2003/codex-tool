#!/usr/bin/env python3
"""Non-network tests: python3 -m unittest discover -s tests -v."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "background.py"
LAUNCHER = ROOT / "codex-launcher"


class BackgroundPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.codex_home = self.base / ".codex"
        self.state = self.base / ".config" / "codex-tool"
        self.config = self.codex_home / "config.toml"
        self.settings = self.codex_home / "app-server-daemon" / "settings.json"

    def run_helper(self, action, success=True):
        result = subprocess.run(
            [sys.executable, str(HELPER), action,
             "--codex-home", str(self.codex_home),
             "--config-dir", str(self.state)],
            capture_output=True, text=True,
        )
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def test_missing_config_is_restored_to_absence(self):
        self.run_helper("optimize")
        self.assertTrue(self.config.exists())
        self.assertTrue(self.settings.exists())
        self.assertTrue((self.state / "background" / "manifest.json").exists())
        self.run_helper("native")
        self.assertFalse(self.config.exists())
        self.assertFalse(self.settings.exists())
        self.assertFalse((self.state / "background" / "manifest.json").exists())

    def test_preserves_other_toml_edits_during_restore(self):
        self.config.parent.mkdir(parents=True)
        self.config.write_text(
            '# original\nmodel = "gpt-6"\n\n[features]\ndaemon_auto_start = true\n',
            encoding="utf-8")
        self.run_helper("optimize")
        content = self.config.read_text()
        self.config.write_text(content.replace('model = "gpt-6"', 'model = "gpt-6-mini"'))
        self.run_helper("native")
        restored = self.config.read_text()
        self.assertIn('model = "gpt-6-mini"', restored)
        self.assertIn("daemon_auto_start = true", restored)
        self.assertNotIn("check_for_update_on_startup = false", restored)

    def test_json_nested_settings_and_other_edits(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(json.dumps({
            "remoteControlEnabled": True,
            "updater": {"autoUpdateEnabled": True, "updateIntervalMinutes": 30},
            "shutdownGraceSeconds": 45,
        }))
        self.run_helper("optimize")
        data = json.loads(self.settings.read_text())
        self.assertIs(data["remoteControlEnabled"], False)
        self.assertIs(data["updater"]["autoUpdateEnabled"], False)
        data["shutdownGraceSeconds"] = 30
        self.settings.write_text(json.dumps(data))
        self.run_helper("native")
        data = json.loads(self.settings.read_text())
        self.assertIs(data["remoteControlEnabled"], True)
        self.assertIs(data["updater"]["autoUpdateEnabled"], True)
        self.assertEqual(data["updater"]["updateIntervalMinutes"], 30)
        self.assertEqual(data["shutdownGraceSeconds"], 30)

    def test_manually_restored_native_value_is_accepted(self):
        self.config.parent.mkdir(parents=True)
        self.config.write_text("[features]\ndaemon_auto_start = true\n")
        self.run_helper("optimize")
        self.config.write_text(self.config.read_text().replace(
            "daemon_auto_start = false", "daemon_auto_start = true"))
        self.run_helper("native")
        self.assertFalse((self.state / "background" / "manifest.json").exists())
        self.assertIn("daemon_auto_start = true", self.config.read_text())

    def test_duplicate_toml_rejected_without_edit(self):
        self.config.parent.mkdir(parents=True)
        duplicate = "[features]\ndaemon_auto_start = true\ndaemon_auto_start = false\n"
        self.config.write_text(duplicate)
        self.run_helper("optimize", success=False)
        self.assertEqual(self.config.read_text(), duplicate)
        self.assertFalse((self.state / "background" / "manifest.json").exists())

    def test_launcher_routing(self):
        tool = self.base / "scripts" / "codex-tool"
        binary = tool / "current" / "bin" / "codex"
        binary.parent.mkdir(parents=True)
        binary.write_text('#!/bin/sh\nprintf "<%s>" "$@"\n')
        binary.chmod(0o755)
        env = dict(os.environ, CODEX_TOOL_HOME=str(tool))
        cases = [
            ([], "<--no-daemon>"),
            (["--yolo"], "<--no-daemon><--yolo>"),
            (["resume", "--last"], "<resume><--no-daemon><--last>"),
            (["fork", "--last"], "<fork><--no-daemon><--last>"),
            (["exec", "hello"], "<exec><hello>"),
            (["app-server", "daemon", "stop"], "<app-server><daemon><stop>"),
            (["agents"], "<agents>"),
        ]
        for argv, expected in cases:
            with self.subTest(argv=argv):
                result = subprocess.run(
                    ["bash", str(LAUNCHER), *argv],
                    env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, expected)


if __name__ == "__main__":
    unittest.main()
