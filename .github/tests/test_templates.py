"""Protect metadata-derived badges and project discovery from regressions."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ENGINE = Path(__file__).resolve().parents[2]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ENGINE / ".scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


readme = load("readme", "readme.py")
project = load("project", "project.py")


class ProjectTemplates(unittest.TestCase):
    def test_app_badges_follow_mounts_arches_and_ingress(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "sample"
            app.mkdir()
            (app / "config.yaml").write_text(
                "name: Sample\nslug: sample\nversion: '2.3.4'\n"
                "url: https://github.com/seb5594/Home-Assistant-Sample-Addon\n"
                "arch: [amd64, armv7]\nmap: ['config:ro', 'share:ro']\n"
                "ingress: true\n")
            kind, folder, metadata = project.discover(root)
            self.assertEqual((kind, folder, metadata["version"]), ("app", app, "2.3.4"))
            badges = readme.project(root)
            for item in ("version-2.3.4", "armv7-supported", "mount-config",
                         "mount-share", "ingress-enabled", "buymeacoffee.com/seb5594"):
                self.assertIn(item, badges)
            self.assertNotIn("i386-supported", badges)
            self.assertNotIn("mount-local%20disks", badges)

    def test_hacs_button_uses_actual_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "custom_components/demo"
            folder.mkdir(parents=True)
            (folder / "manifest.json").write_text(json.dumps({
                "domain": "demo", "version": "1.2.3",
                "documentation": "https://github.com/seb5594/demo-integration"}))
            badges = readme.project(root)
            self.assertIn("owner=seb5594&repository=demo-integration&category=integration", badges)
            self.assertNotIn("ingress-enabled", badges)

    def test_ambiguous_projects_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("app-a", "app-b"):
                (root / name).mkdir()
                (root / name / "config.yaml").write_text("slug: example\n")
            with self.assertRaisesRegex(ValueError, "exactly one"):
                project.discover(root)
