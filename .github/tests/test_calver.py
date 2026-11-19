"""Calendar versions of integrations: no suffix on the first build of a day."""
import json
import tempfile
import unittest
from pathlib import Path

import support  # noqa: F401

import calver


class NextVersion(unittest.TestCase):
    def test_the_first_build_of_a_day_has_no_suffix(self):
        self.assertEqual(calver.next_version(None, "2026.11.19"), "2026.11.19")
        self.assertEqual(calver.next_version("2026.11.18.3", "2026.11.19"), "2026.11.19")
        self.assertEqual(calver.next_version("2026.11.18", "2026.11.19"), "2026.11.19")

    def test_later_builds_of_the_same_day_count_from_one(self):
        self.assertEqual(calver.next_version("2026.11.19", "2026.11.19"), "2026.11.19.1")
        self.assertEqual(calver.next_version("2026.11.19.1", "2026.11.19"), "2026.11.19.2")
        self.assertEqual(calver.next_version("2026.11.19.9", "2026.11.19"), "2026.11.19.10")

    def test_the_version_never_moves_backwards(self):
        self.assertEqual(calver.next_version("2026.11.20", "2026.11.19"), "2026.11.20.1")

    def test_a_legacy_zero_build_is_followed_by_build_one(self):
        self.assertEqual(calver.next_version("2026.11.19.0", "2026.11.19"), "2026.11.19.1")

    def test_other_version_shapes_are_rejected(self):
        with self.assertRaises(ValueError):
            calver.next_version("1.2.3", "2026.11.19")

    def test_the_result_sorts_after_its_predecessor_as_a_version(self):
        from packaging.version import Version
        order = ["2026.11.19", "2026.11.19.1", "2026.11.19.2", "2026.11.19.10", "2026.11.20"]
        self.assertEqual(sorted(order, key=Version), order)


class Release(unittest.TestCase):
    def test_both_spellings_are_releases_and_get_a_tag(self):
        import common
        import package_integration
        for version in ("2026.11.19", "2026.11.19.1"):
            self.assertFalse(common.is_prerelease(version))
            self.assertEqual(common.release_title(version), f"v{version}")
            self.assertTrue(package_integration.VERSION.fullmatch(version))


class Bump(unittest.TestCase):
    def write(self, root, version):
        path = root / "custom_components/demo/manifest.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"domain": "demo", "version": version}, indent=2) + "\n")
        return path

    def test_bump_rewrites_only_the_version(self):
        root = Path(tempfile.mkdtemp())
        path = self.write(root, "2026.11.19")
        self.assertEqual(calver.bump(root, "2026.11.19"), {str(path): "2026.11.19.1"})
        self.assertEqual(json.loads(path.read_text()), {"domain": "demo", "version": "2026.11.19.1"})

    def test_integrations_with_another_version_scheme_are_left_alone(self):
        root = Path(tempfile.mkdtemp())
        path = self.write(root, "1.2.3")
        self.assertEqual(calver.bump(root, "2026.11.19"), {})
        self.assertEqual(json.loads(path.read_text())["version"], "1.2.3")


if __name__ == "__main__":
    unittest.main()
