"""Narrowing the minimum Home Assistant version between a failed and a passed release."""
import unittest

import support  # noqa: F401

import ha_minimum
import ha_refine


def files(day):
    return [{"upload_time": f"2022-{day}T10:00:00", "yanked": False}]


CORE = {"releases": {
    "2022.4.7": files("04-20"), "2022.5.0": files("05-04"), "2022.5.5": files("05-20"),
    "2022.6.0": files("06-01"), "2022.7.0": files("07-06"), "2022.8.0": files("08-03"),
    "2022.8.7": files("08-30"), "2022.9.0b1": files("09-01"), "2022.7.1": [],
}}
PLUGINS = {"releases": {"0.9.0": files("05-06"), "0.10.0": files("06-03"), "0.11.0": files("08-05")}}
INFOS = {
    ("pytest-homeassistant-custom-component", "0.9.0"): "2022.5.0",
    ("pytest-homeassistant-custom-component", "0.10.0"): "2022.6.0",
    ("pytest-homeassistant-custom-component", "0.11.0"): "2022.8.0",
}


def fetch(package, version=None):
    if package == "homeassistant" and version is None:
        return CORE
    if package == "pytest-homeassistant-custom-component" and version is None:
        return PLUGINS
    if package == "homeassistant":
        return {"info": {"requires_python": ">=3.9.0"}}
    return {"info": {"version": version, "requires_python": ">=3.9",
                     "requires_dist": [f"homeassistant (=={INFOS[(package, version)]})", "pytest"]}}


class Boundary(unittest.TestCase):
    def results(self, *items):
        return [{"homeassistant": v, "preview": False, "passed": ok} for v, ok in items]

    def test_the_gap_lies_between_the_last_failure_and_the_start_of_the_passing_run(self):
        data = self.results(("2021.11.5", False), ("2022.4.7", False), ("2022.8.7", True), ("2026.11.0", True))
        self.assertEqual(ha_minimum.boundary(data), ("2022.4.7", "2022.8.7"))

    def test_there_is_no_gap_when_everything_passes_or_the_newest_fails(self):
        self.assertIsNone(ha_minimum.boundary(self.results(("2022.4.7", True), ("2026.11.0", True))))
        self.assertIsNone(ha_minimum.boundary(self.results(("2022.4.7", True), ("2026.11.0", False))))


class Candidates(unittest.TestCase):
    def test_every_series_in_the_gap_is_tested_at_its_first_release(self):
        published = ha_refine.stable_versions(CORE)
        self.assertEqual(ha_refine.gap_candidates("2022.4.7", "2022.8.7", published),
                         ["2022.5.0", "2022.6.0", "2022.7.0", "2022.8.0"])

    def test_yanked_and_preview_releases_are_ignored(self):
        self.assertNotIn("2022.9.0b1", ha_refine.stable_versions(CORE))
        self.assertNotIn("2022.7.1", ha_refine.stable_versions(CORE))

    def test_a_target_uses_the_plugin_that_pins_exactly_that_core(self):
        target = ha_refine.build_target("2022.6.0", CORE, PLUGINS, fetch)
        self.assertEqual((target["plugin"], target["python"]), ("0.10.0", "3.9"))

    def test_a_series_without_matching_plugin_is_skipped(self):
        self.assertIsNone(ha_refine.build_target("2022.7.0", CORE, PLUGINS, fetch))
        self.assertIsNone(ha_refine.series_target("2022.7.0", CORE, PLUGINS, fetch))

    def test_a_series_falls_back_to_a_later_release_a_plugin_exists_for(self):
        key = ("pytest-homeassistant-custom-component", "0.9.0")
        original = INFOS[key]
        INFOS[key] = "2022.5.5"  # the plugin of that series pins the second release, not the first
        plugins = {"releases": {**PLUGINS["releases"], "0.9.0": files("05-22")}}
        try:
            target = ha_refine.series_target("2022.5.0", CORE, plugins, fetch)
        finally:
            INFOS[key] = original
        self.assertEqual(target["homeassistant"], "2022.5.5")


class Exact(unittest.TestCase):
    def test_the_declared_minimum_gets_a_target_of_its_own(self):
        target = ha_refine.exact_target("2022.6.0", fetch)
        self.assertEqual((target["homeassistant"], target["plugin"], target["note"]),
                         ("2022.6.0", "0.10.0", "declared minimum"))

    def test_an_unknown_or_unmatched_declaration_gets_none(self):
        self.assertIsNone(ha_refine.exact_target("2099.1.0", fetch))
        self.assertIsNone(ha_refine.exact_target("2022.7.0", fetch))


class KeepDeclared(unittest.TestCase):
    def test_a_declared_minimum_inside_the_gap_survives_a_run_without_search(self):
        pair = ("2026.2.3", "2026.9.4")
        self.assertTrue(ha_minimum.keep_declared(pair, "2026.3.0"))
        self.assertTrue(ha_minimum.keep_declared(pair, "2026.9.0"))
        self.assertFalse(ha_minimum.keep_declared(pair, "2026.2.0"))   # below: it fails
        self.assertFalse(ha_minimum.keep_declared(pair, "2026.11.0"))  # above: the boundary is lower
        self.assertFalse(ha_minimum.keep_declared(None, "2026.3.0"))
        self.assertFalse(ha_minimum.keep_declared(pair, None))


class Pins(unittest.TestCase):
    def test_releases_before_2026_1_get_the_pycares_pin(self):
        old = ha_refine.build_target("2022.6.0", CORE, PLUGINS, fetch)
        self.assertIn("pycares<5", old["pins"])


    def test_every_subset_of_the_pins_is_offered_largest_first(self):
        target = {"homeassistant": "2025.6.0", "pins": ["josepy<2", "aiohasupervisor==0.2.2b5"]}
        sets = [variant.get("pins", []) for variant in ha_minimum.pin_variants(target)]
        self.assertEqual(sets, [["josepy<2", "aiohasupervisor==0.2.2b5"], ["josepy<2"],
                                ["aiohasupervisor==0.2.2b5"], []])

    def test_a_target_without_pins_has_one_variant(self):
        self.assertEqual(ha_minimum.pin_variants({"homeassistant": "2025.6.0"}), [{"homeassistant": "2025.6.0"}])


class Bisect(unittest.TestCase):
    def run_search(self, first_passing):
        asked = []

        def passes(target):
            asked.append(target["homeassistant"])
            return ha_minimum.version_key(target["homeassistant"]) >= ha_minimum.version_key(first_passing)

        return ha_refine.refine("2022.4.7", "2022.8.7", passes, fetch), asked

    def test_the_first_passing_series_is_found_with_few_runs(self):
        found, asked = self.run_search("2022.6.0")
        self.assertEqual(found, "2022.6.0")
        self.assertLessEqual(len(asked), 2)  # 2022.7.0 has no plugin, three candidates remain

    def test_when_even_the_passed_series_fails_at_its_first_release_the_passed_release_stays(self):
        found, _ = self.run_search("2022.8.7")
        self.assertEqual(found, "2022.8.7")

    def test_a_candidate_that_cannot_be_installed_is_skipped_not_failed(self):
        asked = []

        def passes(candidate):
            asked.append(candidate)
            return None if candidate == "c" else candidate >= "b"

        self.assertEqual(ha_refine.bisect(["a", "b", "c", "d"], passes), "b")
        self.assertIn("c", asked)

    def test_bisect_returns_none_when_nothing_passes(self):
        self.assertIsNone(ha_refine.bisect(["a", "b"], lambda _: False))


if __name__ == "__main__":
    unittest.main()
