"""The follower of upstream releases: version steps, pins on two registries, and its managed workflow."""
import tempfile
import unittest
from pathlib import Path

from support import ENGINE  # noqa: F401

import managed
import upstream

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


if __name__ == "__main__":
    unittest.main()
