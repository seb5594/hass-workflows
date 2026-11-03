"""Live version discovery must not silently miss new Core releases."""
import json
import unittest
from unittest import mock

from support import ENGINE  # noqa: F401
import ha_discovery
import ha_matrix


class Discovery(unittest.TestCase):
    def payload(self, versions):
        return {"releases": {version: [{"yanked": False}] for version in versions}}

    def test_latest_stable_and_each_upcoming_preview_channel(self):
        core = self.payload(["2026.9.4", "2026.10.3", "2026.10.4", "2026.10.0b1",
                             "2026.11.0a1", "2026.11.0a2", "2026.11.0b1", "2026.11.0rc1"])
        core["releases"]["2026.12.0"] = [{"yanked": True}]
        core["releases"]["2027.1.0"] = []
        plugin = {"info": {"version": "0.13.375", "requires_python": ">=3.14",
                           "requires_dist": ["homeassistant==2026.10.4"]}}

        def fetch(package, version=None):
            if package != "homeassistant":
                return plugin
            return core if version is None else {"info": {"requires_python": ">=3.14.2"}}

        with mock.patch.object(ha_discovery, "fetch", side_effect=fetch):
            targets = ha_discovery.discover()
        self.assertEqual([item["homeassistant"] for item in targets],
                         ["2026.10.4", "2026.11.0a2", "2026.11.0b1", "2026.11.0rc1"])
        self.assertTrue(all(item["python"] == "3.14" for item in targets))
        self.assertFalse(targets[0]["override_core"])
        self.assertTrue(all(item["preview"] and item["override_core"] for item in targets[1:]))

    def test_network_failure_is_not_a_successful_static_fallback(self):
        with mock.patch.object(ha_discovery, "fetch", side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
                ha_discovery.discover()

    def test_stable_keeps_matching_fixtures_when_latest_plugin_tracks_beta(self):
        newer = {"version": "0.13.376", "requires_python": ">=3.14", "requires_dist": ["homeassistant==2026.11.0b4"]}
        older = {**newer, "version": "0.13.375", "requires_dist": ["homeassistant==2026.10.4"]}

        def fetch(package, version=None):
            if package == "homeassistant":
                return self.payload(["2026.10.4", "2026.11.0b4"]) if version is None else {"info": {"requires_python": ">=3.14"}}
            if version:
                return {"info": older if version == "0.13.375" else newer}
            return {**self.payload(["0.13.375", "0.13.376"]), "info": newer}

        with mock.patch.object(ha_discovery, "fetch", side_effect=fetch):
            targets = ha_discovery.discover()
        self.assertEqual([item["plugin"] for item in targets], ["0.13.375", "0.13.376"])
        self.assertFalse(any(item["override_core"] for item in targets))

    def test_versions_sort_before_the_final_release(self):
        versions = ["2026.11.0", "2026.11.0rc1", "2026.11.0b10", "2026.11.0a1", "2026.11.0.dev1"]
        self.assertEqual(sorted(versions, key=ha_matrix.version_key), list(reversed(versions)))

    def test_frozen_target_runs_without_rediscovery(self):
        target = {"homeassistant": "2026.11.0b2", "plugin": "0.13.375", "python": "3.14", "live": True}
        with mock.patch.object(ha_matrix, "test_release", return_value={"real": True}) as test:
            self.assertEqual(ha_matrix.main(["run", "--target-json", json.dumps(target)]), 0)
        self.assertEqual(test.call_args.args[0], target)

    def test_live_install_keeps_requested_core_during_dependency_install(self):
        import os
        import tempfile
        from pathlib import Path
        target = {"homeassistant": "2026.11.0b2", "plugin": "0.13.375", "python": "3.14", "live": True}
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {"HASS_MATRIX_DIR": directory}):
            def run(command, **options):
                if command[:2] == ["uv", "venv"]:
                    Path(command[-1]).mkdir(parents=True)
                return mock.Mock(stdout="aiohttp\n", returncode=0)
            with mock.patch.object(ha_matrix, "run", side_effect=run) as commands:
                ha_matrix.prepare(target, ["http"], [])
            installs = [call.args[0] for call in commands.call_args_list if call.args[0][:3] == ["uv", "pip", "install"]]
            self.assertEqual(len(installs), 2)
            self.assertTrue(all("--override" in command for command in installs))
            self.assertIn("homeassistant==2026.11.0b2", installs[0])
            self.assertNotIn("setuptools<70", installs[0])


if __name__ == "__main__":
    unittest.main()
