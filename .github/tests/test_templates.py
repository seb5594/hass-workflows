"""Protect project discovery, README badges and the caller templates."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from support import ENGINE

import badgekit
import project
import readme

APP_CONFIG = (
    "name: Sample\nslug: sample\nversion: '2.3.4'\n"
    "url: https://github.com/seb5594/Home-Assistant-Sample-Addon\n"
    "arch: [amd64, armv7]\nstartup: once\nmap:\n  - config:ro\n  - type: share\n    read_only: false\n"
    "ingress: true\noptions:\n  group:\n    a: 1\n    b: 2\n")


def make_app(root):
    app = root / "sample"
    app.mkdir()
    (app / "config.yaml").write_text(APP_CONFIG)
    (app / "Dockerfile").write_text("ARG BUILD_FROM=alpine:3.24.2\nFROM ${BUILD_FROM}\n")
    return app


class ProjectBadges(unittest.TestCase):
    def test_app_badges_follow_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = make_app(root)
            kind, folder, metadata = project.discover(root)
            self.assertEqual((kind, folder, metadata["version"]), ("app", app, "2.3.4"))
            block = readme.render(root)
            for item in ("message=2.3.4", "message=amd64%20%C2%B7%20armv7", "label=read-only", "message=config",
                         "label=read-write", "message=share", "message=enabled",
                         "buymeacoffee.com/seb5594"):
                self.assertIn(item, block)
            self.assertNotIn("i386", block)
            for removed in ("label=startup", "label=boot", "label=supervisor", "label=base"):
                self.assertNotIn(removed, block)
            self.assertIn("message=2", block)  # leaf option count, not group count

    def test_rows_are_tight_and_donations_stand_alone_at_the_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_app(root)
            body = readme.render(root).splitlines()[1:-1]
            self.assertNotIn("", body)
            self.assertGreaterEqual(len(body), 6)
            self.assertTrue(all(line.endswith("<br>") for line in body[:-1]))
            last = body[-1]
            self.assertIn("buymeacoffee.com", last)
            self.assertNotIn("supervisor_add_addon_repository", last)

    def test_hacs_button_uses_actual_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "custom_components/demo"
            folder.mkdir(parents=True)
            (folder / "manifest.json").write_text(json.dumps({
                "domain": "demo", "version": "1.2.3b1", "config_flow": True, "iot_class": "local_polling",
                "bluetooth": [{"local_name": "demo*"}],
                "documentation": "https://github.com/seb5594/demo-integration"}))
            (root / "hacs.json").write_text(json.dumps({"homeassistant": "2026.9.0"}))
            block = readme.render(root)
            self.assertIn("owner=seb5594&repository=demo-integration&category=integration", block)
            self.assertIn("message=%E2%89%A5%202026.9.0", block)
            self.assertIn("label=setup", block)
            for removed in ("label=stage", "label=type", "label=iot%20class", "label=discovery",
                            "label=requirements"):
                self.assertNotIn(removed, block)
            rows = block.splitlines()[1:-1]
            self.assertIn("label=HACS", rows[0])
            self.assertIn("label=setup", rows[0])
            self.assertIn("label=home%20assistant", rows[1])
            self.assertIn("label=version", rows[1])
            self.assertIn("label=downloads", rows[2])
            self.assertIn("label=stars", rows[3])

    def test_hacs_badge_leads_in_its_own_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "custom_components/demo"
            folder.mkdir(parents=True)
            (folder / "manifest.json").write_text(json.dumps({
                "domain": "demo", "version": "1.0.0", "documentation": "https://github.com/seb5594/demo-integration"}))
            (root / "hacs.json").write_text("{}")
            first = readme.render(root).splitlines()[1]
            self.assertIn("label=HACS", first)
            self.assertEqual(first.count("!["), 1)

    def test_update_inserts_and_checks_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_app(root)
            (root / "README.md").write_text("# Sample\n\nText\n")
            with self.assertRaises(ValueError):
                readme.verify(root)
            self.assertTrue(readme.update(root))
            readme.verify(root)
            self.assertFalse(readme.update(root))
            self.assertTrue((root / "README.md").read_text().startswith("# Sample\n\n" + readme.START))

    def test_ambiguous_projects_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("app-a", "app-b"):
                (root / name).mkdir()
                (root / name / "config.yaml").write_text("slug: example\n")
            with self.assertRaisesRegex(ValueError, "exactly one"):
                project.discover(root)


class LiveFacts(unittest.TestCase):
    EMPTY = {"stars": 0, "forks": 0, "issues": 0, "releases": 0, "downloads": 0,
             "latest_downloads": 0, "builds": 0, "metrics": set()}

    def rows(self, **facts):
        manifest = {"domain": "demo", "version": "1.0.0", "config_flow": True}
        rows = badgekit.integration_rows(manifest, {"homeassistant": "2026.9.0"}, "seb5594/demo",
                                         live={**self.EMPTY, **facts})
        return badgekit.render(rows)

    def test_badges_without_a_value_are_hidden(self):
        block = self.rows()
        for hidden in ("label=stars", "label=forks", "label=issues", "label=released", "label=downloads",
                       "label=checks", "tests.json", "last-build.json"):
            self.assertNotIn(hidden, block)
        for kept in ("label=version", "label=updated", "label=HACS", "label=home%20assistant"):
            self.assertIn(kept, block)

    def test_badges_with_a_value_are_shown(self):
        block = self.rows(stars=3, forks=1, issues=2, releases=1, downloads=5, latest_downloads=5, builds=4,
                          metrics={"tests", "last-build", "zip-size"})
        for shown in ("label=stars", "label=forks", "label=issues", "label=released", "label=downloads",
                      "label=latest%20release", "label=checks", "tests.json", "zip-size.json"):
            self.assertIn(shown, block)

    def test_latest_release_downloads_hide_independently(self):
        block = self.rows(downloads=9, latest_downloads=0)
        self.assertIn("label=downloads", block)
        self.assertNotIn("label=latest%20release", block)


class BadgeLayout(unittest.TestCase):
    def test_every_layout_entry_has_a_builder(self):
        for layout, builders in ((badgekit.APP_LAYOUT, badgekit._app_builders()),
                                 (badgekit.INTEGRATION_LAYOUT, badgekit._integration_builders())):
            for name in (name for row in layout for name in row):
                self.assertIn(name, builders)


class StyleOptions(unittest.TestCase):
    def test_options_come_from_pyproject(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous = Path.cwd()
            try:
                os.chdir(tmp)
                self.assertIsNone(project.pycodestyle_options())
                Path(".github/dev").mkdir(parents=True)
                Path(".github/dev/pyproject.toml").write_text(
                    '[tool.pycodestyle]\nmax-line-length = 100\nignore = ["E501", "W503"]\n')
                self.assertEqual(project.pycodestyle_options(),
                                 ["--max-line-length=100", "--ignore=E501,W503"])
            finally:
                os.chdir(previous)


class PublishDecision(unittest.TestCase):
    base = {"PUBLISH": "true", "EVENT_NAME": "push", "REF": "refs/heads/main", "DEFAULT_BRANCH": "main"}

    def test_default_branch_and_version_tags_publish(self):
        self.assertTrue(project.should_publish(self.base))
        self.assertTrue(project.should_publish({**self.base, "REF": "refs/tags/v1.0.0"}))

    def test_other_refs_and_pull_requests_do_not(self):
        self.assertFalse(project.should_publish({**self.base, "REF": "refs/heads/dev"}))
        self.assertFalse(project.should_publish({**self.base, "EVENT_NAME": "pull_request"}))
        self.assertFalse(project.should_publish({**self.base, "PUBLISH": "false"}))

    def test_template_repositories_never_publish(self):
        self.assertFalse(project.should_publish({**self.base, "IS_TEMPLATE": "true"}))


class CallerTemplates(unittest.TestCase):
    def test_templates_pin_one_engine_commit_and_pass_secrets(self):
        for kind in ("app", "integration"):
            text = (ENGINE / f".templates/{kind}/ci.yml.tpl").read_text()
            self.assertEqual(text.count("__ENGINE_SHA__"), 1)
            self.assertIn("secrets.ORCHESTRATION_PAT", text)

    def test_caller_drift_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            workflow = Path(tmp) / ".github/workflows/ci.yml"
            workflow.parent.mkdir(parents=True)
            sha = "a" * 40
            template = (ENGINE / ".templates/app/ci.yml.tpl").read_text()
            workflow.write_text(template.replace("__ENGINE_SHA__", sha))
            previous = Path.cwd()
            try:
                os.chdir(tmp)
                project.check_caller_workflow("app")
                workflow.write_text(workflow.read_text() + "# local edit\n")
                with self.assertRaisesRegex(ValueError, "differs"):
                    project.check_caller_workflow("app")
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
