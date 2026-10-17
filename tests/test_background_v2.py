"""Offline tests for the v2 live state reconciliation engine."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    import background_v2 as engine
    import tomlkit
except ImportError:
    engine = None

@unittest.skipIf(engine is None, "tomlkit dependency unavailable")
class ReconciliationTests(unittest.TestCase):
    def test_toml_tree_edit_comments_and_format(self):
        original = ('model="gpt-6"\n[features]\n'
                    'multi_agent = true\n'
                    '\n[mcp_servers.example]\ncommand="node"\n')
        changes = {k: {"present": True, "value": False} for k in engine.TOML_KEYS}
        rendered = engine.edit_toml(original, changes, True)
        self.assertIn("daemon_auto_start = false", rendered)
        self.assertIn("# codex-tool:", rendered)
        self.assertEqual(rendered, engine.edit_toml(rendered, changes, True))
        restored = {k: {"present": False, "value": None} for k in engine.TOML_KEYS}
        result = engine.edit_toml(rendered, restored, False)
        self.assertEqual(engine.parse_toml(result).unwrap(), engine.parse_toml(original).unwrap())
        self.assertNotIn("# codex-tool:", result)

    def test_overriding_effective_config(self):
        response = {"read": {"config": {"features": {"daemon_auto_start": True}},
                             "origins": {"features.daemon_auto_start": {"name": {"type": "project"}}}}}
        self.assertTrue(engine.effective_key(response, "features.daemon_auto_start"))
        self.assertEqual(engine.origin_key(response, "features.daemon_auto_start")["name"]["type"], "project")

    def test_live_status_ignores_manifest_for_config_classification(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            conf = home / "config.toml"
            settings = home / "app-server-daemon" / "settings.json"
            conf.parent.mkdir(parents=True)
            settings.parent.mkdir(parents=True)
            conf.write_text("check_for_update_on_startup = false\n[features]\ndaemon_auto_start = false\n")
            settings.write_text(json.dumps({"remoteControlEnabled": False, "updater": {"autoUpdateEnabled": False}}))
            args = type("Args", (), {"codex_home": str(home), "config_dir": td, "no_api": True, "cwd": None})()
            state = engine.collect(args)
            self.assertEqual(state["config"], "optimized")
            conf.write_text("check_for_update_on_startup = true\n[features]\ndaemon_auto_start = false\n")
            state = engine.collect(args)
            self.assertNotEqual(state["config"], "optimized")

if __name__ == "__main__":
    unittest.main()
