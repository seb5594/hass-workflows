"""Image naming and metric badges."""
import json
import unittest
from unittest import mock

from support import ENGINE  # noqa: F401

import badgekit
import common
import metrics


class ImageNaming(unittest.TestCase):
    def test_architecture_tag_follows_scheme(self):
        self.assertEqual(common.image_tag("git-exporter", "1.18", "amd64"), "amd64-hass-git-exporter-v1.18")

    def test_multi_arch_tag_drops_architecture(self):
        self.assertEqual(common.image_tag("git-exporter", "1.18"), "hass-git-exporter-v1.18")

    def test_repository_is_lowercase(self):
        self.assertEqual(common.image_repository("Seb5594", "rsync-local"), "ghcr.io/seb5594/hass-rsync-local")


class MetricBadges(unittest.TestCase):
    def test_formatting(self):
        self.assertEqual(metrics.size(17 * 1024 * 1024 + 800_000), "17.8 MiB")
        self.assertEqual(metrics.duration(252), "4m 12s")
        self.assertEqual(metrics.duration(9), "9s")

    def test_badges_cover_recorded_values(self):
        recorded = {"image_size.amd64": 16 * 1024 * 1024, "runtime_tests": 12, "tests": 202, "zip_size": 1024 * 1024}
        with mock.patch.object(metrics, "package_pulls", return_value=1234):
            result = metrics.badges(recorded, "sample", "seb5594")
        self.assertEqual(result["image-size-amd64"][1], "16.0 MiB")
        self.assertEqual(result["runtime-tests"][1], "12 passed")
        self.assertEqual(result["tests"][1], "202 passed")
        self.assertEqual(result["image-pulls"][1], "1,234")
        self.assertIn("last-build", result)

    def test_unreadable_pull_count_is_skipped(self):
        with mock.patch.object(metrics, "package_pulls", return_value=None):
            self.assertNotIn("image-pulls", metrics.badges({}, "sample", "seb5594"))

    def test_pull_count_parser(self):
        page = '<span>Total downloads</span>\n  <h3 title="4321">4.3K</h3>'
        self.assertEqual(int(metrics.DOWNLOADS.search(page).group(1)), 4321)

    def test_endpoint_payload_matches_shields_schema(self):
        payload = json.loads(badgekit.dump_endpoint("tests", "5 passed", "stable"))
        self.assertEqual(payload["schemaVersion"], 1)
        self.assertEqual(payload["color"], badgekit.COLORS["stable"])


if __name__ == "__main__":
    unittest.main()
