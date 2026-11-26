"""Protect release titles, the checksum line in the notes and the assets of a release."""
import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support  # noqa: F401

import common
import package_integration
import release_app


class RegistryPush(unittest.TestCase):
    def test_a_transient_blob_error_retries_the_same_tested_image(self):
        error = subprocess.CalledProcessError(1, ["docker", "push", "image:tag"])
        with mock.patch.object(release_app, "run", side_effect=[error, None]) as runner, \
                mock.patch.object(release_app.time, "sleep") as sleep:
            release_app.push_image("image:tag")
        self.assertEqual(runner.call_count, 2)
        self.assertEqual(runner.call_args_list[0], runner.call_args_list[1])
        sleep.assert_called_once_with(1)

    def test_an_unrecoverable_registry_error_stops_after_four_attempts(self):
        error = subprocess.CalledProcessError(1, ["docker", "push", "image:tag"])
        with mock.patch.object(release_app, "run", side_effect=error) as runner, \
                mock.patch.object(release_app.time, "sleep") as sleep:
            with self.assertRaises(subprocess.CalledProcessError):
                release_app.push_image("image:tag")
        self.assertEqual(runner.call_count, 4)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2, 4])


class ReleaseTitles(unittest.TestCase):
    def test_stable_versions_are_titled_by_their_version_only(self):
        self.assertEqual(common.release_title("1.2.0"), "v1.2.0")
        self.assertEqual(common.release_title("1.74.3"), "v1.74.3")

    def test_a_build_number_does_not_change_the_title(self):
        self.assertEqual(common.release_title("2026.10.20.0"), "2026.10.20.0")
        self.assertEqual(common.release_title("2026.10.20.0b2"), "Beta 2")

    def test_prereleases_are_titled_by_their_stage(self):
        for version, title in (("1.0.0b3", "Beta 3"), ("1.0.0a1", "Alpha 1"), ("2.1.0rc2", "RC 2"),
                               ("1.0.0-beta4", "Beta 4"), ("1.0.0-beta.4", "Beta 4"),
                               ("1.0.0-rc.1", "RC 1"), ("1.0.0-alpha", "Alpha")):
            self.assertEqual(common.release_title(version), title, version)

    def test_the_title_never_contains_the_project_name_or_the_numeric_base(self):
        self.assertNotIn("1.0.0", common.release_title("1.0.0b3"))


class IntegrationVersions(unittest.TestCase):
    def test_accepted_shapes(self):
        for version in ("1.2.0", "1.0.0b3", "2.1.0rc2", "2026.10.20.0", "2026.7.14.3", "2026.10.20.1a1"):
            self.assertTrue(package_integration.VERSION.fullmatch(version), version)

    def test_rejected_shapes(self):
        for version in ("1.2", "1.2.3.4.5", "1.2.0-beta", "v1.2.0", "2026.10.20."):
            self.assertFalse(package_integration.VERSION.fullmatch(version), version)

    def test_a_build_number_is_not_a_prerelease(self):
        self.assertFalse(common.is_prerelease("2026.10.20.3"))
        self.assertTrue(common.is_prerelease("2026.10.20.3b1"))


class ReleaseFlags(unittest.TestCase):
    """A stable release is pinned as the latest explicitly; a pre-release never is."""

    def flags(self, version, draft=False, prerelease=None):
        with mock.patch.dict(os.environ, {"RELEASE_DRAFT": "true" if draft else ""}):
            return common.release_flags(version, prerelease)

    def test_a_stable_release_is_marked_latest(self):
        self.assertEqual(self.flags("2026.11.25.14"), ["--latest"])
        self.assertEqual(self.flags("1.2.0"), ["--latest"])

    def test_a_prerelease_is_marked_prerelease_and_never_latest(self):
        flags = self.flags("1.0.0b3")
        self.assertIn("--prerelease", flags)
        self.assertNotIn("--latest", flags)

    def test_a_draft_stable_release_is_not_pinned_latest(self):
        # A draft is unpublished and cannot be the latest release.
        self.assertEqual(self.flags("1.2.0", draft=True), ["--draft"])

    def test_a_beta_forced_regular_is_pinned_latest(self):
        # When the caller overrides the marker (a first beta published as a regular release), it is
        # the latest so catalogs and installers find it.
        self.assertEqual(self.flags("1.0.0b3", prerelease=False), ["--latest"])


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

    def publish(self, version, notes="## What's Changed\n* A change", hacs=None, existing=None, stable=False, prefix="v"):
        """Run publish() with GitHub mocked; returns the (create) call and all `run` calls."""
        def gh_json(*args):
            return existing if args[1] == "view" else None
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self.archive(out)
            with mock.patch.dict(os.environ, {"GITHUB_REPOSITORY": "o/r", "GITHUB_SHA": "a" * 40}), \
                    mock.patch.object(package_integration, "gh_json", side_effect=gh_json), \
                    mock.patch.object(package_integration, "stable_version_released", return_value=stable), \
                    mock.patch.object(package_integration, "generated_notes", return_value=notes), \
                    mock.patch.object(package_integration, "run") as run:
                package_integration.publish(f"{prefix}{version}", {"name": "Demo", "version": version},
                                            hacs or {}, out)
            self.run_calls = run.call_args_list
            return run.call_args

    def test_release_is_titled_by_its_version_and_ends_with_the_checksum(self):
        call = self.publish("1.2.0")
        args = list(call.args)
        self.assertEqual(args[args.index("--title") + 1], "v1.2.0")
        self.assertEqual(args[args.index("--notes-file") + 1], "-")
        lines = call.kwargs["input"].splitlines()
        self.assertEqual(lines[0], "## What's Changed")
        self.assertTrue(lines[-1].startswith("SHA256 `demo.zip`: `"))

    def test_unprefixed_release_keeps_the_exact_tag_and_title(self):
        args = list(self.publish("2026.11.07.1", prefix="").args)
        self.assertEqual(args[3], "2026.11.07.1")
        self.assertEqual(args[args.index("--title") + 1], "2026.11.07.1")

    def test_only_the_archive_is_uploaded_not_a_checksum_file(self):
        args = [str(arg) for arg in self.publish("1.2.0").args]
        uploads = [arg for arg in args if arg.endswith((".zip", ".txt"))]
        self.assertEqual([Path(arg).name for arg in uploads], ["demo.zip"])

    def test_prerelease_is_marked_and_titled_by_its_stage(self):
        args = list(self.publish("1.0.0b3").args)
        self.assertEqual(args[args.index("--title") + 1], "Beta 3")
        self.assertIn("--prerelease", args)
        self.assertIn("v1.0.0b3", args)

    def test_a_first_beta_with_zip_release_is_published_as_a_regular_release(self):
        zip_release = {"zip_release": True, "filename": "demo.zip"}
        args = list(self.publish("1.0.0b3", hacs=zip_release, stable=False).args)
        self.assertEqual(args[args.index("--title") + 1], "Beta 3")
        self.assertNotIn("--prerelease", args)

    def test_an_existing_release_keeps_its_assets_but_follows_the_marker_rule(self):
        zip_release = {"zip_release": True, "filename": "demo.zip"}
        self.publish("1.0.0b3", hacs=zip_release, existing={"isPrerelease": True}, stable=False)
        self.assertEqual([call.args[:3] for call in self.run_calls], [("gh", "release", "edit")])
        self.assertIn("--prerelease=false", self.run_calls[0].args)

    def test_a_regular_release_without_a_latest_release_is_made_the_latest(self):
        zip_release = {"zip_release": True, "filename": "demo.zip"}
        self.publish("1.0.0b3", hacs=zip_release, existing={"isPrerelease": False}, stable=False)
        self.assertEqual(self.run_calls[0].args[-1], "--latest")
        self.assertNotIn("--prerelease=false", self.run_calls[0].args)

    def test_an_existing_release_in_line_with_the_rule_is_left_alone(self):
        self.publish("1.0.0b3", existing={"isPrerelease": True})
        self.assertEqual(self.run_calls, [])

    def test_a_release_without_generated_notes_still_ends_with_the_checksum(self):
        notes = self.publish("1.2.0", notes="").kwargs["input"]
        self.assertTrue(notes.startswith("SHA256 `demo.zip`"))


class HacsSettings(unittest.TestCase):
    ZIP = {"zip_release": True, "filename": "demo.zip"}

    def test_zip_release_is_optional(self):
        package_integration.check_hacs({"name": "Demo"}, "demo")

    def test_a_zip_release_must_name_the_archive_the_engine_builds(self):
        package_integration.check_hacs(self.ZIP, "demo")
        with self.assertRaisesRegex(AssertionError, "demo.zip"):
            package_integration.check_hacs({"zip_release": True, "filename": "other.zip"}, "demo")


class PrereleaseMarker(unittest.TestCase):
    """HACS counts the ZIP of a stable release only, so a beta must not hide behind the marker alone."""
    ZIP = {"zip_release": True, "filename": "demo.zip"}

    def marked(self, hacs, version, stable):
        with mock.patch.object(package_integration, "stable_version_released", return_value=stable):
            return package_integration.marked_prerelease(hacs, version, "o/r")

    def test_stable_versions_are_never_marked(self):
        self.assertFalse(self.marked(self.ZIP, "1.0.0", stable=True))
        self.assertFalse(self.marked({}, "1.0.0", stable=False))

    def test_a_beta_without_any_stable_release_is_regular_while_zip_release_is_set(self):
        self.assertFalse(self.marked(self.ZIP, "1.0.0b3", stable=False))

    def test_a_beta_after_a_stable_release_is_marked(self):
        self.assertTrue(self.marked(self.ZIP, "1.1.0b1", stable=True))

    def test_a_project_without_zip_release_marks_its_betas(self):
        self.assertTrue(self.marked({}, "1.0.0b3", stable=False))

    def test_stable_versions_are_told_from_betas_by_their_tag(self):
        releases = [{"tagName": "v1.0.0b3", "isDraft": False}, {"tagName": "v1.0.0b2", "isDraft": False}]
        with mock.patch.object(package_integration, "gh_json", return_value=releases):
            self.assertFalse(package_integration.stable_version_released("o/r"))
        with mock.patch.object(package_integration, "gh_json",
                               return_value=releases + [{"tagName": "v1.0.0", "isDraft": False}]):
            self.assertTrue(package_integration.stable_version_released("o/r"))
        with mock.patch.object(package_integration, "gh_json",
                               return_value=[{"tagName": "v1.0.0", "isDraft": True}]):
            self.assertFalse(package_integration.stable_version_released("o/r"))


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


class RegistryMigration(unittest.TestCase):
    def test_registry_override_keeps_slug_tags_and_owner_scope(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch('common.Path', side_effect=lambda name: Path(folder)/name):
            root=Path(folder);(root/'.github').mkdir()
            self.assertEqual(common.image_repository('Example','tuya_breaker'),'ghcr.io/example/hass-tuya_breaker-app')
            (root/'.github/images.json').write_text(json.dumps({'tuya_breaker':'hass-tuya-breaker'}))
            self.assertEqual(common.image_repository('Example','tuya_breaker'),'ghcr.io/example/hass-tuya-breaker-app')
            (root/'.github/images.json').write_text(json.dumps({'tuya_breaker':'hass-tuya-breaker-app'}))
            self.assertEqual(common.image_repository('Example','tuya_breaker'),'ghcr.io/example/hass-tuya-breaker-app')
            self.assertEqual(common.image_tag('tuya_breaker','1.0.0'),'hass-tuya_breaker-v1.0.0')
            (root/'.github/images.json').write_text(json.dumps({'tuya_breaker':'other-owner/package'}))
            with self.assertRaises(ValueError):common.image_repository('Example','tuya_breaker')
