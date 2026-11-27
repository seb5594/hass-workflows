"""The minimum Home Assistant version that hacs.json derives from the matrix results."""
import json
import tempfile
import unittest
from pathlib import Path

import support  # noqa: F401

import ha_minimum


def result(version, passed, preview=False):
    return {"homeassistant": version, "preview": preview, "passed": passed}


class ChooseMinimum(unittest.TestCase):
    def test_everything_passing_keeps_the_exact_oldest_tested_patch(self):
        results = [result("2021.11.5", True), result("2022.4.7", True), result("2026.11.0", True)]
        self.assertEqual(ha_minimum.choose_minimum(results), "2021.11.5")

    def test_the_minimum_is_the_next_release_that_passed_above_a_failure(self):
        results = [result("2021.11.5", False), result("2022.4.7", False), result("2022.8.7", True),
                   result("2023.1.7", True), result("2026.11.0", True)]
        self.assertEqual(ha_minimum.choose_minimum(results), "2022.8.7")

    def test_a_gap_in_the_middle_raises_the_minimum_above_it(self):
        results = [result("2021.11.5", True), result("2022.8.7", False), result("2022.12.8", True),
                   result("2026.11.0", True)]
        self.assertEqual(ha_minimum.choose_minimum(results), "2022.12.8")

    def test_a_failing_newest_stable_release_is_a_regression_and_changes_nothing(self):
        results = [result("2021.11.5", True), result("2026.9.4", True), result("2026.11.0", False)]
        self.assertIsNone(ha_minimum.choose_minimum(results))

    def test_previews_never_decide(self):
        results = [result("2021.11.5", True), result("2026.11.0", True), result("2026.12.0b1", False, True)]
        self.assertEqual(ha_minimum.choose_minimum(results), "2021.11.5")

    def test_missing_results_change_nothing(self):
        results = [result("2022.4.7", True), result("2026.11.0", True)]
        self.assertIsNone(ha_minimum.choose_minimum(results, ["2021.11.5", "2022.4.7", "2026.11.0"]))
        self.assertEqual(ha_minimum.choose_minimum(results, ["2022.4.7", "2026.11.0"]), "2022.4.7")

    def test_unknown_environment_outcome_never_moves_the_floor(self):
        self.assertIsNone(ha_minimum.choose_minimum([result("2022.4.0", None), result("2026.11.3", True)]))

    def test_no_stable_result_changes_nothing(self):
        self.assertIsNone(ha_minimum.choose_minimum([]))
        self.assertIsNone(ha_minimum.choose_minimum([result("2026.12.0b1", True, True)]))


class Gate(unittest.TestCase):
    def test_only_failures_the_project_claims_are_errors(self):
        root = Path(tempfile.mkdtemp())
        (root / "hacs.json").write_text('{"homeassistant": "2022.8.0"}')
        old, new = {"homeassistant": "2022.4.7"}, {"homeassistant": "2022.8.7"}
        self.assertEqual(ha_minimum.gate(old, "failure", root), 0)
        self.assertEqual(ha_minimum.gate(new, "failure", root), 1)
        self.assertEqual(ha_minimum.gate(new, "success", root), 0)

    def test_without_a_declared_minimum_every_failure_counts(self):
        self.assertEqual(ha_minimum.gate({"homeassistant": "2022.4.7"}, "failure", Path(tempfile.mkdtemp())), 1)


class Files(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_results_round_trip_through_files(self):
        ha_minimum.record(self.root / "r", {"homeassistant": "2022.4.7"}, "success")
        ha_minimum.record(self.root / "r", {"homeassistant": "2026.12.0b1", "preview": True}, "failure")
        self.assertEqual(ha_minimum.load(self.root / "r"),
                         [result("2022.4.7", True), result("2026.12.0b1", False, True)])

    def test_hacs_json_keeps_its_layout_and_other_keys(self):
        (self.root / "hacs.json").write_text('{\n  "name": "X",\n  "homeassistant": "2023.2.0",\n  "render_readme": true\n}\n')
        self.assertTrue(ha_minimum.write_minimum("2022.8.0", self.root))
        text = (self.root / "hacs.json").read_text()
        self.assertEqual(json.loads(text), {"name": "X", "homeassistant": "2022.8.0", "render_readme": True})
        self.assertIn('\n  "name"', text)
        self.assertFalse(ha_minimum.write_minimum("2022.8.0", self.root))

    def test_a_repository_without_hacs_json_is_left_alone(self):
        self.assertFalse(ha_minimum.write_minimum("2022.8.0", self.root))


if __name__ == "__main__":
    unittest.main()
