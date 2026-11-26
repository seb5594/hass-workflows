"""Which Home Assistant releases a project is tested against, and how."""
import io
import json
import os
import tempfile
import unittest
import datetime
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

    def test_button_era_target_requires_an_explicit_compatible_minimum(self):
        target = "2021.12.10"
        versions = lambda minimum=None: {
            item["homeassistant"] for item in ha_matrix.releases(minimum)
        }
        self.assertIn(target, versions(target))
        self.assertIn(target, versions("2022.1.0") | versions(target))
        self.assertNotIn(target, versions("2022.1.0"))

    def test_the_support_line_trails_today_by_five_years(self):
        day = datetime.date.fromisoformat
        self.assertEqual(ha_matrix.support_line(day("2026-11-18")), (2021, 11))
        self.assertEqual(ha_matrix.support_line(day("2026-11-03")), (2021, 10))  # .0 may not be out yet
        self.assertEqual(ha_matrix.support_line(day("2027-01-05")), (2021, 12))
        self.assertEqual(ha_matrix.support_line(day("2024-02-29")), (2019, 2))

    def test_the_tested_range_defaults_to_five_years_without_a_declaration(self):
        day = datetime.date.fromisoformat
        self.assertEqual(ha_matrix.supported_minimum(None, day("2026-11-18")), "2021.11.5")
        # The curated release at or below the line is chosen, never one above it.
        self.assertEqual(ha_matrix.supported_minimum(None, day("2027-06-20")), "2022.4.7")
        self.assertEqual(ha_matrix.supported_minimum(None, day("2027-12-20")), "2022.12.8")

    def test_an_older_declared_minimum_is_kept_but_a_newer_one_never_shortens_the_range(self):
        late = datetime.date(2027, 12, 20)
        self.assertEqual(ha_matrix.supported_minimum("2021.11.0", late), "2021.11.0")
        for minimum in ("2023.6.0", "2026.3.0"):
            with self.subTest(minimum=minimum):
                self.assertEqual(ha_matrix.supported_minimum(minimum, late), "2022.12.8")

    def test_invalid_declarations_do_not_silently_fall_back_to_the_window(self):
        with self.assertRaises(ValueError):
            ha_matrix.supported_minimum("invalid")

    def test_the_declared_time_entity_floor_has_an_exact_core_fixture_target(self):
        first = ha_matrix.releases("2023.6.0")[0]
        self.assertEqual((first["homeassistant"], first["plugin"], first["python"]),
                         ("2023.6.0", "0.13.36", "3.10"))

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

    def test_projects_with_real_tests_run_the_whole_window_whatever_they_declare(self):
        self.write(".github/ha_tests/test_real.py")
        self.write("hacs.json", json.dumps({"homeassistant": "2026.3.0"}))
        with mock.patch.object(ha_matrix, "supported_minimum", wraps=ha_matrix.supported_minimum) as chosen:
            listed = self.listed()
        self.assertEqual(listed[0], ha_matrix.supported_minimum("2026.3.0"))
        self.assertEqual(listed[-4:], ["2025.1.4", "2025.12.4", "2026.2.3", "2026.9.4"])
        chosen.assert_called_once_with("2026.3.0")
        self.assertEqual(self.listed("--minimum", "2026.9.0"), ["2026.9.4"])


class Commands(InProject):
    def test_the_regular_suite_keeps_the_home_assistant_plugin_out_and_honours_the_project_config(self):
        self.write(".github/dev/pyproject.toml")
        command = ha_matrix.pytest_command("python", Path(".github/tests"), real=False)
        self.assertIn("no:homeassistant", command)
        self.assertEqual(Path(command[command.index("-c") + 1]), Path(".github/dev/pyproject.toml"))

    def test_the_real_suite_needs_the_plugin_and_automatic_asyncio(self):
        command = ha_matrix.pytest_command("python", Path(".github/ha_tests"), real=True)
        self.assertNotIn("no:homeassistant", command)
        self.assertIn("hass_real_tests", command)
        self.assertIn("asyncio_mode=auto", command)
        self.assertIn("import homeassistant; import pytest,sys; sys.exit(pytest.main(sys.argv[1:]))", command)

    def test_a_finished_environment_is_reused(self):
        release = {"homeassistant": "2023.2.5", "plugin": "0.12.57", "python": "3.10"}
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, {"HASS_MATRIX_DIR": folder}):
            (Path(folder) / "2023.2.5").mkdir()
            (Path(folder) / "2023.2.5/.prepared").write_text(json.dumps(
                {"release": release, "plugin_package": "pytest-homeassistant-custom-component",
                 "domains": ["bluetooth"], "requirements": []}, sort_keys=True))
            with mock.patch.object(ha_matrix, "run") as run:
                interpreter = ha_matrix.prepare(release, ["bluetooth"], [])
            run.assert_not_called()
            self.assertEqual(interpreter, Path(folder) / "2023.2.5/bin/python")

    def test_withdrawn_legacy_typing_dependency_does_not_block_core_tests(self):
        release = {"homeassistant": "2024.4.0", "plugin": "0.13.111", "python": "3.12"}
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, {"HASS_MATRIX_DIR": folder}):
            (Path(folder) / "2024.4.0").mkdir()
            metadata = {"info": {"requires_dist": [
                "homeassistant==2024.4.0", "pytest==8.1.1", "mypy-dev==1.10.0a3",
            ]}}
            with mock.patch.object(ha_matrix, "run", return_value=mock.Mock(stdout="")) as runner, \
                    mock.patch("ha_discovery.fetch", return_value=metadata):
                ha_matrix.prepare(release, [], [])
            install = [call.args[0] for call in runner.call_args_list if call.args[0][:3] ==
                       ["uv", "pip", "install"]]
            self.assertTrue(any("homeassistant==2024.4.0" in args and "pytest==8.1.1" in args
                                for args in install))
            self.assertTrue(any("--no-deps" in args and
                                "pytest-homeassistant-custom-component==0.13.111" in args
                                for args in install))
            self.assertFalse(any("mypy-dev==1.10.0a3" in args for args in install))


if __name__ == "__main__":
    unittest.main()
