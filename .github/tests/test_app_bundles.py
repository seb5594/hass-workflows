"""Explicit app bundles build every member and publish one complete release."""
import contextlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support  # noqa: F401
import managed
import project
import projectmeta
import release_app


@contextlib.contextmanager
def checkout():
    previous = Path.cwd()
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        for name in ("main-app", "wifi-helper"):
            folder = root / name
            folder.mkdir()
            (folder / "config.yaml").write_text(
                f"name: {name}\nslug: {name}\nversion: 0.1.1-beta.1\n"
                "url: https://github.com/owner/project\narch: [amd64, aarch64]\n")
            (folder / "CHANGELOG.md").write_text("# Changelog\n\n## 0.1.1-beta.1\n")
            (folder / "entrypoint.sh").write_text("placeholder\n")
        (root / ".github").mkdir()
        (root / ".github/apps.json").write_text(json.dumps({"apps": ["main-app", "wifi-helper"]}))
        os.chdir(root)
        try:
            yield root
        finally:
            os.chdir(previous)


class AppBundleTests(unittest.TestCase):
    def test_explicit_order_selects_primary_without_ignoring_the_helper(self):
        with checkout() as root:
            self.assertEqual(projectmeta.discover(root).slug, "main-app")
            self.assertEqual([app.slug for app in projectmeta.app_projects(root)], ["main-app", "wifi-helper"])

    def test_unlisted_duplicate_unknown_and_traversal_members_are_rejected(self):
        with checkout() as root:
            for names in (["main-app"], ["main-app", "main-app"], ["main-app", "missing"],
                          ["main-app", "../wifi-helper"], [], "main-app"):
                (root / ".github/apps.json").write_text(json.dumps({"apps": names}))
                with self.subTest(names=names), self.assertRaises(ValueError):
                    projectmeta.discover(root)

    def test_multiple_apps_still_need_an_explicit_manifest(self):
        with checkout() as root:
            (root / ".github/apps.json").unlink()
            with self.assertRaisesRegex(ValueError, "exactly one"):
                projectmeta.discover(root)

    def test_bundle_versions_and_repository_must_agree(self):
        for old, new in (("0.1.1-beta.1", "0.2.0"), ("owner/project", "owner/other")):
            with checkout() as root:
                config = root / "wifi-helper/config.yaml"
                config.write_text(config.read_text().replace(old, new))
                with self.assertRaisesRegex(ValueError, "same version and repository"):
                    projectmeta.discover(root)

    def test_managed_files_cover_both_apps_and_one_caller(self):
        with checkout() as root:
            files = managed.expected("app", "a" * 40, root)
            self.assertIn("main-app/entrypoint.sh", files)
            self.assertIn("wifi-helper/entrypoint.sh", files)
            self.assertIn(".github/workflows/ci.yml", files)

    def test_build_visits_every_app_architecture_and_keeps_primary_metrics(self):
        with checkout(), mock.patch.object(project, "run") as run:
            project.main("build")
            calls = run.call_args_list
            self.assertEqual([(Path(c.args[2]).name, c.args[3]) for c in calls],
                             [("main-app", "amd64"), ("main-app", "aarch64"),
                              ("wifi-helper", "amd64"), ("wifi-helper", "aarch64")])
            self.assertEqual(calls[0].kwargs["env"]["APP_METRICS_PREFIX"], "")
            self.assertEqual(calls[-1].kwargs["env"]["APP_METRICS_PREFIX"], "app.wifi-helper.")

    def test_release_attaches_all_four_image_references_once(self):
        with checkout(), mock.patch.dict(os.environ, {
            "GITHUB_REPOSITORY": "owner/project", "GITHUB_REF": "refs/heads/dev", "GITHUB_SHA": "b" * 40
        }), mock.patch.object(release_app, "release_exists", return_value=False), \
                mock.patch.object(release_app, "run") as run, mock.patch.object(release_app.gitops, "notify"):
            release_app.main("main-app", "wifi-helper")
            calls = [c.args for c in run.call_args_list]
            manifests = [c for c in calls if c[:4] == ("docker", "buildx", "imagetools", "create")]
            releases = [c for c in calls if c[:3] == ("gh", "release", "create")]
            self.assertEqual(len(manifests), 2)
            self.assertTrue(all(not any(str(arg).endswith(":latest") for arg in call) for call in manifests))
            self.assertEqual(len(releases), 1)
            self.assertIn("--prerelease", releases[0])
            references = [Path(arg) for arg in releases[0] if str(arg).endswith(".json")]
            self.assertEqual(len(references), 4)
            self.assertEqual({json.loads(path.read_text())["platform"] for path in references},
                             {"linux/amd64", "linux/arm64"})

    def test_mismatched_versions_cannot_publish_any_image(self):
        with checkout() as root, mock.patch.object(release_app, "run") as run:
            config = root / "wifi-helper/config.yaml"
            config.write_text(config.read_text().replace("0.1.1-beta.1", "0.2.0"))
            with self.assertRaisesRegex(ValueError, "same release version"):
                release_app.main("main-app", "wifi-helper")
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
