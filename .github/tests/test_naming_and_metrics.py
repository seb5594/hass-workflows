"""Image naming and pipeline measurements."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from support import ENGINE  # noqa: F401

import common
import metrics
import release_app


class ImageNaming(unittest.TestCase):
    def test_architecture_tag_follows_scheme(self):
        self.assertEqual(common.image_tag("git-exporter", "1.18", "amd64"), "amd64-hass-git-exporter-v1.18")

    def test_multi_arch_tag_drops_architecture(self):
        self.assertEqual(common.image_tag("git-exporter", "1.18"), "hass-git-exporter-v1.18")

    def test_repository_is_lowercase(self):
        self.assertEqual(common.image_repository("Seb5594", "rsync-local"), "ghcr.io/seb5594/hass-rsync-local")


class ImagePublishing(unittest.TestCase):
    def test_each_architecture_is_retagged_and_described(self):
        config = {"slug": "git-exporter", "version": "1.18.1", "arch": ["amd64", "armv7"]}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(release_app, "run") as run:
            assets = Path(tmp)
            references = release_app.push_architecture_images(
                config, Path("git-exporter"), "ghcr.io/seb5594/hass-git-exporter", assets)
            description = json.loads((assets / "armv7-hass-git-exporter-v1.18.1.json").read_text())
        self.assertEqual(references, [
            "ghcr.io/seb5594/hass-git-exporter:amd64-hass-git-exporter-v1.18.1",
            "ghcr.io/seb5594/hass-git-exporter:armv7-hass-git-exporter-v1.18.1"])
        run.assert_any_call("docker", "tag", "local/git-exporter:amd64", references[0])
        run.assert_any_call("docker", "push", references[1])
        self.assertEqual(description["platform"], "linux/arm/v7")


class Measurements(unittest.TestCase):
    def test_formatting(self):
        self.assertEqual(metrics.human_size(17 * 1024 * 1024 + 800_000), "17.8 MiB")
        self.assertEqual([metrics.compact_count(n) for n in (7, 1234, 1000, 2_500_000)], ["7", "1.2k", "1k", "2.5M"])

    def test_new_values_replace_old_ones_and_missing_ones_are_kept(self):
        previous = {"tests": 10, "image_pulls": 1200, "zip_size": 4000}
        merged = metrics.merge(previous, {"tests": 12, "image_size.amd64": 5 * 1024 * 1024, "image_pulls": None})
        self.assertEqual(merged, {"tests": 12, "image_pulls": 1200, "zip_size": 4000,
                                  "image_size": {"amd64": 5 * 1024 * 1024}})

    def test_changes_the_badge_would_not_show_are_ignored(self):
        previous = {"image_pulls": 1210, "zip_size": 40_000}
        self.assertEqual(metrics.merge(previous, {"image_pulls": 1240, "zip_size": 40_100}), previous)
        self.assertEqual(metrics.merge(previous, {"image_pulls": 1300})["image_pulls"], 1300)

    def test_snapshot_is_written_only_when_it_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, store = Path(tmp), Path(tmp) / "run.json"
            with mock.patch.object(metrics, "RUN_STORE", store), \
                    mock.patch.object(metrics, "package_pulls", return_value=4321):
                metrics.record("tests", 5)
                self.assertTrue(metrics.update_snapshot(root, "sample", "seb5594"))
                self.assertFalse(metrics.update_snapshot(root, "sample", "seb5594"))
            self.assertEqual(metrics.load(root), {"tests": 5, "image_pulls": 4321})

    def test_unreadable_pull_count_keeps_the_previous_value(self):
        with mock.patch.object(metrics, "package_pulls", return_value=None):
            self.assertEqual(metrics.merge({"image_pulls": 9}, {"image_pulls": metrics.package_pulls("o", "p")}),
                             {"image_pulls": 9})

    def test_pull_count_parser(self):
        page = '<span>Total downloads</span>\n  <h3 title="4321">4.3K</h3>'
        self.assertEqual(int(metrics.DOWNLOADS.search(page).group(1)), 4321)


if __name__ == "__main__":
    unittest.main()
