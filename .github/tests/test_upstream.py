"""The follower of upstream releases: version steps, pins on two registries, and its managed workflow."""
import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

from support import ENGINE  # noqa: F401

import managed
import upstream
import validate_app

HUB = "# renovate: datasource=docker depName=docker.io/gitea/runner\nARG RUNNER_VERSION=5.2.2\n"
GHCR = "# renovate: datasource=docker depName=ghcr.io/raylabshq/gitea-mirror\nARG MIRROR_VERSION=v3.46.0\n"
SUFFIXED = "# renovate: datasource=docker depName=docker.io/oven/bun\nARG BUN_VERSION=1.3.14-alpine\n"


class Versions(unittest.TestCase):
    def test_calendar_builds_increment_per_day_and_never_go_backwards(self):
        self.assertEqual(upstream.next_version("2026-10-27", today="2026-10-27"), "2026-10-27.2")
        self.assertEqual(upstream.next_version("2026-10-27.9", today="2026-10-27"), "2026-10-27.10")
        self.assertEqual(upstream.next_version("2026-10-27.9", today="2026-10-28"), "2026-10-28")
        self.assertEqual(upstream.next_version("2026-10-27.2", today="2026-10-26"), "2026-10-27.3")

    def test_prereleases_count_up_and_releases_get_a_patch_number(self):
        self.assertEqual(upstream.next_version("1.0.0-alpha.9"), "1.0.0-alpha.10")
        self.assertEqual(upstream.next_version("1.0.0-dev3"), "1.0.0-dev4")
        self.assertEqual(upstream.next_version("1.2.3"), "1.2.4")
        with self.assertRaises(SystemExit):
            upstream.next_version("2.0.0-beta.1")

    def test_pins_on_both_registries_are_followed_and_suffixed_ones_are_left_to_renovate(self):
        found = {(m["registry"], m["repository"], m["version"]) for m in upstream.PIN.finditer(HUB + GHCR + SUFFIXED)}
        self.assertEqual(found, {("docker.io", "gitea/runner", "5.2.2"), ("ghcr.io", "raylabshq/gitea-mirror", "v3.46.0")})

    def test_a_v_prefix_does_not_change_the_order(self):
        self.assertGreater(upstream.as_tuple("v3.46.1"), upstream.as_tuple("v3.46.0"))
        self.assertGreater(upstream.as_tuple("v3.10.0"), upstream.as_tuple("3.9.9"))


class Releasing(unittest.TestCase):
    def test_the_version_and_the_changelog_are_raised_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp)
            (app / "config.yaml").write_text('name: x\nversion: "1.0.0-alpha.1"\n')
            (app / "Dockerfile").write_text("ARG BUILD_VERSION=1.0.0-alpha.1\n" + GHCR)
            (app / "CHANGELOG.md").write_text("# Changelog\n\n## 1.0.0-alpha.1\n\n* first\n")
            version = upstream.release_app(app, "Update gitea-mirror to 3.47.0.")
            self.assertEqual(version, "1.0.0-alpha.2")
            self.assertIn('version: "1.0.0-alpha.2"', (app / "config.yaml").read_text())
            self.assertIn("ARG BUILD_VERSION=1.0.0-alpha.2", (app / "Dockerfile").read_text())
            self.assertTrue((app / "CHANGELOG.md").read_text().startswith(
                "# Changelog\n\n## 1.0.0-alpha.2\n\n* Update gitea-mirror to 3.47.0.\n"))


class ManagedWorkflow(unittest.TestCase):
    def files(self, dockerfile):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "demo").mkdir()
            (root / "demo/config.yaml").write_text("name: Demo\nslug: demo\nversion: '1'\narch: [amd64]\n")
            (root / "demo/Dockerfile").write_text(dockerfile)
            return managed.expected("app", "a" * 40, root)

    def test_apps_with_a_followed_image_get_the_workflow_pinned_to_the_engine(self):
        files = self.files("ARG BUILD_FROM=x:1\n" + GHCR)
        self.assertIn("a" * 40, files[".github/workflows/upstream.yml"])
        self.assertIn("./.engine/.actions/follow-upstream", files[".github/workflows/upstream.yml"])

    def test_other_apps_do_not(self):
        self.assertNotIn(".github/workflows/upstream.yml", self.files("ARG BUILD_FROM=x:1\n"))


class AlignedVersions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / ".github").mkdir()
        (root / ".github/upstream.json").write_text(json.dumps({
            "versionArgument": "MIRROR_VERSION", "majorUpdates": "approval"}))
        self.app = root / "mirror"
        self.app.mkdir()
        (self.app / "config.yaml").write_text(
            'name: Mirror\nslug: mirror\nversion: "3.46.0"\narch: [amd64]\n')
        (self.app / "Dockerfile").write_text(GHCR + SUFFIXED + "ARG BUILD_VERSION=3.46.0\n")
        (self.app / "CHANGELOG.md").write_text("# Changelog\n\n## 3.46.0\n\n* Existing entry.\n")

    def test_follower_updates_same_major_even_when_a_new_major_exists(self):
        with patch.object(upstream, "ghcr_tags", return_value=["v3.46.0", "v3.51.6", "v4.0.0"]):
            upstream.update(self.app)
        self.assertEqual(upstream.read_version((self.app / "config.yaml").read_text()), "3.51.6")
        self.assertIn("ARG MIRROR_VERSION=v3.51.6", (self.app / "Dockerfile").read_text())
        self.assertIn("ARG BUILD_VERSION=3.51.6", (self.app / "Dockerfile").read_text())
        self.assertIn("## 3.51.6", (self.app / "CHANGELOG.md").read_text())

    def test_major_only_release_does_not_touch_any_files(self):
        before = {p.name: p.read_bytes() for p in self.app.iterdir()}
        with patch.object(upstream, "ghcr_tags", return_value=["v3.46.0", "v4.0.0"]):
            upstream.update(self.app)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.app.iterdir()})

    def test_approved_pin_in_pull_request_sets_the_exact_upstream_version(self):
        dockerfile = self.app / "Dockerfile"
        dockerfile.write_text(dockerfile.read_text().replace("MIRROR_VERSION=v3.46.0", "MIRROR_VERSION=v4.0.0"))
        upstream.bump(self.app, "Reviewed upstream major update.", None)
        self.assertEqual(upstream.read_version((self.app / "config.yaml").read_text()), "4.0.0")

    def test_packaging_update_does_not_claim_a_nonexistent_upstream_patch(self):
        before = {p.name: p.read_bytes() for p in self.app.iterdir()}
        with patch.object(upstream, "write_output") as output:
            upstream.bump(self.app, "Base image update.", None)
        output.assert_called_once_with(False, "3.46.0")
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.app.iterdir()})

    def test_managed_major_rule_survives_template_regeneration(self):
        files = managed.expected("app", "a" * 40, self.app.parent)
        rule = json.loads(files[".github/renovate.json"])["packageRules"][-1]
        self.assertEqual(rule["matchDatasources"], ["docker"])
        self.assertEqual(rule["matchUpdateTypes"], ["major"])
        self.assertTrue(rule["dependencyDashboardApproval"])
        self.assertFalse(rule["automerge"])
        self.assertIsNone(rule["groupName"])

    def test_docker_hub_major_is_also_held_for_review(self):
        with patch.object(upstream, "docker_hub_tags", return_value=["6.0.0", "6.1.0", "7.0.0"]):
            self.assertEqual(upstream.newest_release("docker.io", "gitea/runner", major=6), "6.1.0")

    def test_ci_rejects_metadata_that_does_not_match_the_upstream_pin(self):
        with self.assertRaisesRegex(AssertionError, "must match the primary upstream image"):
            validate_app.check_release_files(self.app, {"version": "1.0.0"},
                                             (self.app / "Dockerfile").read_text())

    def test_invalid_approval_policy_fails_closed(self):
        (self.app.parent / ".github/upstream.json").write_text(
            '{"versionArgument": "MIRROR_VERSION", "majorUpdates": "automatic"}')
        with self.assertRaisesRegex(ValueError, "majorUpdates: approval"):
            upstream.update(self.app)


if __name__ == "__main__":
    unittest.main()
