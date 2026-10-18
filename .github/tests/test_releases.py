"""Protect release titles, the checksum line in the notes and the assets of a release."""
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support  # noqa: F401

import common
import package_integration
import release_app


class ReleaseTitles(unittest.TestCase):
    def test_stable_versions_are_titled_by_their_version_only(self):
        self.assertEqual(common.release_title("1.2.0"), "v1.2.0")
        self.assertEqual(common.release_title("1.74.3"), "v1.74.3")

    def test_prereleases_are_titled_by_their_stage(self):
        for version, title in (("1.0.0b3", "Beta 3"), ("1.0.0a1", "Alpha 1"), ("2.1.0rc2", "RC 2"),
                               ("1.0.0-beta4", "Beta 4"), ("1.0.0-beta.4", "Beta 4"),
                               ("1.0.0-rc.1", "RC 1"), ("1.0.0-alpha", "Alpha")):
            self.assertEqual(common.release_title(version), title, version)

    def test_the_title_never_contains_the_project_name_or_the_numeric_base(self):
        self.assertNotIn("1.0.0", common.release_title("1.0.0b3"))


class IntegrationRelease(unittest.TestCase):
    def archive(self, folder):
        path = Path(folder) / "demo.zip"
        path.write_bytes(b"zip content")
        return path

    def test_checksum_is_one_line_naming_the_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.archive(tmp)
            line = package_integration.checksum_line([path])
        self.assertEqual(line, f"SHA256 `demo.zip`: `{hashlib.sha256(b'zip content').hexdigest()}`")
        self.assertNotIn("\n", line)

    def publish(self, version, notes="## What's Changed\n* A change"):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self.archive(out)
            missing = mock.Mock(returncode=1)
            with mock.patch.dict(os.environ, {"GITHUB_REPOSITORY": "o/r", "GITHUB_SHA": "a" * 40}), \
                    mock.patch.object(package_integration.subprocess, "run", return_value=missing), \
                    mock.patch.object(package_integration, "generated_notes", return_value=notes), \
                    mock.patch.object(package_integration, "run") as run:
                package_integration.publish(f"v{version}", {"name": "Demo", "version": version}, out)
            return run.call_args

    def test_release_is_titled_by_its_version_and_ends_with_the_checksum(self):
        call = self.publish("1.2.0")
        args = list(call.args)
        self.assertEqual(args[args.index("--title") + 1], "v1.2.0")
        self.assertEqual(args[args.index("--notes-file") + 1], "-")
        lines = call.kwargs["input"].splitlines()
        self.assertEqual(lines[0], "## What's Changed")
        self.assertTrue(lines[-1].startswith("SHA256 `demo.zip`: `"))

    def test_only_the_archive_is_uploaded_not_a_checksum_file(self):
        args = [str(arg) for arg in self.publish("1.2.0").args]
        uploads = [arg for arg in args if arg.endswith((".zip", ".txt"))]
        self.assertEqual([Path(arg).name for arg in uploads], ["demo.zip"])

    def test_prerelease_is_marked_and_titled_by_its_stage(self):
        args = list(self.publish("1.0.0b3").args)
        self.assertEqual(args[args.index("--title") + 1], "Beta 3")
        self.assertIn("--prerelease", args)
        self.assertIn("v1.0.0b3", args)

    def test_a_release_without_generated_notes_still_ends_with_the_checksum(self):
        notes = self.publish("1.2.0", notes="").kwargs["input"]
        self.assertTrue(notes.startswith("SHA256 `demo.zip`"))


class AppRelease(unittest.TestCase):
    def create(self, version):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "CHANGELOG.md").write_text("# Changelog\n")
            assets = folder / "dist"
            assets.mkdir()
            with mock.patch.dict(os.environ, {"GITHUB_SHA": "b" * 40}), \
                    mock.patch.object(release_app, "run") as run:
                release_app.create_release({"name": "Demo App", "version": version}, folder, "o/r",
                                           f"v{version}", assets)
            return list(run.call_args.args)

    def test_app_releases_are_titled_like_integration_releases(self):
        args = self.create("1.74.3")
        self.assertEqual(args[args.index("--title") + 1], "v1.74.3")
        self.assertNotIn("--prerelease", args)

    def test_app_prereleases_carry_only_their_stage(self):
        args = self.create("1.0.0-beta.4")
        self.assertEqual(args[args.index("--title") + 1], "Beta 4")
        self.assertIn("--prerelease", args)


if __name__ == "__main__":
    unittest.main()
