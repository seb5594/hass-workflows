"""Protect project discovery, README badges and the caller templates."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from support import ENGINE

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
            for item in ("message=2.3.4", "message=armv7", "label=config", "message=read-only",
                         "label=share", "message=read-write", "message=enabled",
                         "label=base%20image", "alpine%3A3.24.2", "buymeacoffee.com/seb5594"):
                self.assertIn(item, block)
            self.assertNotIn("i386", block)
            self.assertIn("message=2", block)  # leaf option count, not group count

    def test_badges_are_grouped_into_paragraphs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_app(root)
            block = readme.render(root)
            self.assertGreaterEqual(block.count("\n\n"), 5)
            self.assertTrue(all(line.count("![") >= 1 for line in block.splitlines()[1:-1] if line))

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
            for item in ("message=beta", "message=local%20polling", "message=bluetooth"):
                self.assertIn(item, block)

    def test_update_inserts_and_checks_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_app(root)
            (root / "README.md").write_text("# Sample\n\nText\n")
            with self.assertRaises(ValueError):
                readme.update(root, check=True)
            readme.update(root)
            readme.update(root, check=True)
            self.assertTrue((root / "README.md").read_text().startswith("# Sample\n\n" + readme.START))

    def test_ambiguous_projects_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("app-a", "app-b"):
                (root / name).mkdir()
                (root / name / "config.yaml").write_text("slug: example\n")
            with self.assertRaisesRegex(ValueError, "exactly one"):
                project.discover(root)


class PublishDecision(unittest.TestCase):
    base = {"PUBLISH": "true", "EVENT_NAME": "push", "REF": "refs/heads/main", "DEFAULT_BRANCH": "main"}

    def test_default_branch_and_version_tags_publish(self):
        self.assertTrue(project.should_publish(self.base))
        self.assertTrue(project.should_publish({**self.base, "REF": "refs/tags/v1.0.0"}))

    def test_other_refs_and_pull_requests_do_not(self):
        self.assertFalse(project.should_publish({**self.base, "REF": "refs/heads/dev"}))
        self.assertFalse(project.should_publish({**self.base, "EVENT_NAME": "pull_request"}))
        self.assertFalse(project.should_publish({**self.base, "PUBLISH": "false"}))


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
