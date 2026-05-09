from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI = REPO_ROOT / "bin" / "tokenused"
PLUGIN_NAMES = {
    "daily-overview-plugin.py",
    "claude-code-usage-plugin.py",
    "gemini-cli-usage-plugin.py",
    "codex-local-usage-plugin.py",
}


class TokenUsedCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tokenused-cli-"))
        self.usageboard = self.tmp / "UsageBoard"
        self.home = self.tmp / "home"
        self.home.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cli(self, *args: str, repo_root: Path | None = None) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["HOME"] = str(self.home)
        return subprocess.run(
            [
                sys.executable,
                str(CLI),
                "--repo-root",
                str(repo_root or REPO_ROOT),
                "--usageboard-root",
                str(self.usageboard),
                *args,
            ],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

    def test_sync_plugins_copies_repo_plugins_and_preserves_executable_bits(self):
        result = self.run_cli("sync-plugins")

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        installed = self.usageboard / "plugins"
        self.assertTrue(installed.is_dir())
        for name in PLUGIN_NAMES:
            target = installed / name
            source = REPO_ROOT / "plugins" / name
            self.assertTrue(target.exists(), name)
            self.assertEqual(target.read_text(encoding="utf-8"), source.read_text(encoding="utf-8"))
            self.assertTrue(target.stat().st_mode & stat.S_IXUSR, name)

    def test_install_config_creates_config_from_example_with_real_home_paths(self):
        result = self.run_cli("install-config")

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        config = json.loads((self.usageboard / "config.json").read_text(encoding="utf-8"))
        self.assertNotIn("__HOME__", json.dumps(config))
        self.assertEqual(config["language"], "zh-Hans")
        self.assertEqual({p["stateID"] for p in config["plugins"]}, {
            "daily-overview",
            "claude-code-local",
            "gemini-cli-local",
            "codex-local",
        })
        for plugin in config["plugins"]:
            self.assertIn(str(self.home), plugin["executablePath"])

    def test_install_config_upserts_tokenused_plugins_without_clobbering_existing_config(self):
        self.usageboard.mkdir(parents=True)
        config_path = self.usageboard / "config.json"
        config_path.write_text(json.dumps({
            "language": "en",
            "customTopLevel": {"keep": True},
            "plugins": [
                {
                    "stateID": "other-plugin",
                    "name": "Other",
                    "enabled": False,
                    "executablePath": "/tmp/other.py",
                },
                {
                    "stateID": "codex-local",
                    "name": "Old Codex",
                    "enabled": False,
                    "executablePath": "/tmp/old.py",
                },
            ],
        }), encoding="utf-8")

        result = self.run_cli("install-config")

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        merged = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(merged["language"], "en")
        self.assertEqual(merged["customTopLevel"], {"keep": True})
        by_state = {p["stateID"]: p for p in merged["plugins"]}
        self.assertIn("other-plugin", by_state)
        self.assertEqual(by_state["other-plugin"]["executablePath"], "/tmp/other.py")
        self.assertEqual(by_state["codex-local"]["name"], "Codex (本地)")
        self.assertIn(str(self.home), by_state["codex-local"]["executablePath"])
        self.assertEqual(
            [p["stateID"] for p in merged["plugins"]],
            ["other-plugin", "daily-overview", "claude-code-local", "gemini-cli-local", "codex-local"],
        )

    def test_doctor_missing_data_dirs_is_not_failure_after_install(self):
        self.assertEqual(self.run_cli("sync-plugins").returncode, 0)
        self.assertEqual(self.run_cli("install-config").returncode, 0)

        result = self.run_cli("doctor")

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("Python:", result.stdout)
        self.assertIn("UsageBoard config:", result.stdout)
        self.assertIn("Claude data dir: missing", result.stdout)
        self.assertRegex(result.stdout, r"UsageBoard patch: (unknown|applied|not applied)")

    def test_doctor_reports_serious_missing_config_and_plugins_as_nonzero(self):
        result = self.run_cli("doctor")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("UsageBoard config: missing", result.stdout)
        self.assertIn("installed plugins: missing", result.stdout)

    def test_smoke_runs_all_plugins_and_validates_json_schema_version(self):
        result = self.run_cli("smoke")

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(set(report), PLUGIN_NAMES)
        for status in report.values():
            self.assertEqual(status["ok"], True)
            self.assertEqual(status["schemaVersion"], 1)


if __name__ == "__main__":
    unittest.main()
