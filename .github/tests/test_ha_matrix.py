"""Which Home Assistant releases a project is tested against, and how."""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from support import ENGINE  # noqa: F401

import ha_matrix
import hass_real_tests


class InProject(unittest.TestCase):
    """Work inside a scratch project, like the matrix does in a checkout."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        previous = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)

    def write(self, path, content=""):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)


class Releases(InProject):
    def test_the_table_is_ordered_and_names_a_python_and_plugin_for_each_release(self):
        table = ha_matrix.releases()
        versions = [item["homeassistant"] for item in table]
        self.assertEqual(versions, sorted(versions, key=ha_matrix.version_key))
        self.assertTrue(all(item["plugin"] and item["python"] for item in table))

    def test_only_releases_at_or_above_the_minimum_are_used(self):
        versions = [item["homeassistant"] for item in ha_matrix.releases("2024.4.0")]
        self.assertEqual(versions[0], "2024.6.4")
        self.assertNotIn("2023.12.3", versions)
        self.assertEqual(ha_matrix.version_key("2023.12.3") < ha_matrix.version_key("2024.1.0"), True)

    def test_the_minimum_comes_from_hacs_json(self):
        self.assertIsNone(ha_matrix.minimum_from_hacs(self.root))
        self.write("hacs.json", json.dumps({"homeassistant": "2023.2.0"}))
        self.assertEqual(ha_matrix.minimum_from_hacs(self.root), "2023.2.0")

    def test_dependencies_and_requirements_come_from_the_integration_manifest(self):
        self.write("custom_components/demo/manifest.json", json.dumps({
            "dependencies": ["http", "bluetooth"], "after_dependencies": ["usb"], "requirements": ["pulsectl==23.5.2"]}))
        self.assertEqual(ha_matrix.manifest_dependencies(self.root), ["bluetooth", "http", "usb"])
        self.assertEqual(ha_matrix.manifest_requirements(self.root), ["pulsectl==23.5.2"])

    def test_the_real_test_plugin_treats_declared_dependencies_as_loaded(self):
        self.write("custom_components/demo/manifest.json", json.dumps({"dependencies": ["http"], "after_dependencies": ["usb"]}))
        self.write("custom_components/other/manifest.json", json.dumps({"dependencies": ["bluetooth"]}))
        self.assertEqual(hass_real_tests.manifest_dependencies(self.root), {"http", "bluetooth"})


class Listing(InProject):
    def listed(self, *arguments):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(ha_matrix.main(["list", *arguments]), 0)
        return json.loads(output.getvalue())

    def test_projects_without_real_tests_have_nothing_to_run(self):
        self.write("hacs.json", json.dumps({"homeassistant": "2023.2.0"}))
        self.assertEqual(self.listed(), [])

    def test_projects_with_real_tests_run_from_their_minimum_upwards(self):
        self.write(".github/ha_tests/test_real.py")
        self.write("hacs.json", json.dumps({"homeassistant": "2025.1.0"}))
        self.assertEqual(self.listed(), ["2025.1.4", "2025.12.4", "2026.2.3", "2026.9.4"])
        self.assertEqual(self.listed("--minimum", "2026.9.0"), ["2026.9.4"])


class Commands(InProject):
    def test_the_regular_suite_keeps_the_home_assistant_plugin_out_and_honours_the_project_config(self):
        self.write(".github/dev/pyproject.toml")
        command = ha_matrix.pytest_command("python", Path(".github/tests"), real=False)
        self.assertIn("no:homeassistant", command)
        self.assertEqual(command[command.index("-c") + 1], ".github/dev/pyproject.toml")

    def test_the_real_suite_needs_the_plugin_and_automatic_asyncio(self):
        command = ha_matrix.pytest_command("python", Path(".github/ha_tests"), real=True)
        self.assertNotIn("no:homeassistant", command)
        self.assertIn("hass_real_tests", command)
        self.assertIn("asyncio_mode=auto", command)

    def test_a_finished_environment_is_reused(self):
        release = {"homeassistant": "2023.2.5", "plugin": "0.12.57", "python": "3.10"}
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, {"HASS_MATRIX_DIR": folder}):
            (Path(folder) / "2023.2.5").mkdir()
            (Path(folder) / "2023.2.5/.prepared").touch()
            with mock.patch.object(ha_matrix, "run") as run:
                interpreter = ha_matrix.prepare(release, ["bluetooth"], [])
            run.assert_not_called()
            self.assertEqual(interpreter, Path(folder) / "2023.2.5/bin/python")


if __name__ == "__main__":
    unittest.main()
