"""Catalog discovery, pinning and rendering without network access."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from support import ENGINE  # noqa: F401

import catalog

REPOSITORY = "Home-Assistant-Rsync-Local-Addon"


class CatalogTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        patcher = patch.object(catalog, "ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.source = self.root / "Rsync-Local"
        app = self.source / "rsync-local"
        app.mkdir(parents=True)
        (app / "config.yaml").write_text(
            "name: Rsync Local\nversion: '1.74.1'\nslug: rsync-local\n"
            "description: USB backups\narch: [amd64]\nmap: ['config:ro']\ndevices: [/dev/sda1]\n")
        (app / "Dockerfile").write_text("ARG BUILD_FROM=alpine:3.24.2\n")
        (self.source / "README.md").write_text("Back up Home Assistant files.\n")
        self.repo = {"name": REPOSITORY, "default_branch": "main", "description": "USB backups"}
        self.modules = {"Rsync-Local": {"key": "submodule.rsync",
                                        "url": f"https://github.com/seb5594/{REPOSITORY}.git"}}

    def test_nested_app_discovery_ignores_source_workflows(self):
        (self.source / ".github").mkdir()
        (self.source / ".github/config.yaml").write_text("invalid: [")
        self.assertEqual(catalog.app_metadata(self.source)[0]["path"], "rsync-local")

    def test_sync_keeps_root_submodule_and_pins_default_branch(self):
        with patch.object(catalog, "git", return_value="a" * 40) as git:
            entry = catalog.sync_repository(self.repo, self.modules, 500)
        self.assertEqual((entry["path"], entry["commit"]), ("Rsync-Local", "a" * 40))
        git.assert_any_call("fetch", "--depth=1", "origin", "refs/heads/main", cwd=self.source)
        git.assert_any_call("checkout", "--detach", "a" * 40, cwd=self.source)
        self.assertFalse(any(call.args[:2] == ("submodule", "add") for call in git.call_args_list))

    def test_sync_refuses_unmanaged_directory(self):
        with self.assertRaisesRegex(ValueError, "unmanaged"):
            catalog.sync_repository(self.repo, {}, 500)

    def test_managed_paths_reject_unrelated_modules(self):
        unrelated = {"notes": {"key": "submodule.notes", "url": "https://github.com/another/project.git"}}
        self.assertEqual(set(catalog.managed_submodules(self.modules | unrelated)), {"Rsync-Local"})

    def test_rendered_catalog_reflects_declared_features(self):
        entry = {"path": "Rsync-Local", "url": f"https://github.com/seb5594/{REPOSITORY}",
                 "repository": f"seb5594/{REPOSITORY}", "excerpt": "USB backups", "commit": "a" * 40,
                 "items": catalog.app_metadata(self.source)}
        readme = catalog.render_readme([entry])
        for item in ("message=1.74.1", "label=read-only", "label=local%20disks", "Pinned commit",
                     "label=apps", "alpine%3A3.24.2"):
            self.assertIn(item, readme)
        self.assertNotIn("{{", readme)
        self.assertNotIn("buymeacoffee", readme.split("## Available apps")[1])

    def test_repository_metadata_names_the_maintainer_handle(self):
        self.assertIn("maintainer: seb5594", catalog.repository_yaml())


class IntegrationCatalog(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        folder = self.root / "ninebot" / "custom_components/demo"
        folder.mkdir(parents=True)
        (folder / "manifest.json").write_text(
            '{"domain": "demo", "name": "Demo", "version": "1.0.0b1", "iot_class": "local_polling"}')
        (self.root / "ninebot/hacs.json").write_text('{"homeassistant": "2026.9.0"}')
        for name, value in (("KIND", "integrations"), ("NAME_PATTERN", catalog.re.compile(
                catalog.NAME_PATTERNS["integrations"])), ("TEMPLATES", catalog.ENGINE / ".templates/catalog/integrations"),
                            ("CATALOG_REPOSITORY", "seb5594/Home-Assistant-Integrations"), ("ROOT", self.root)):
            patcher = patch.object(catalog, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_integration_repositories_are_recognised(self):
        for name in ("hass-ninebot_e_scooters-integration", "Home-Assistant-Demo-Integration"):
            self.assertTrue(catalog.NAME_PATTERN.fullmatch(name), name)
        for name in ("Home-Assistant-Integrations", "hass-workflows", "Home-Assistant-Demo-Addon"):
            self.assertFalse(catalog.NAME_PATTERN.fullmatch(name), name)

    def test_private_repositories_are_never_discovered(self):
        public = {"name": "hass-a-integration", "owner": {"login": "seb5594"}}
        hidden = [{**public, "name": "hass-b-integration", "private": True},
                  {**public, "name": "hass-c-integration", "archived": True}]
        with patch.object(catalog, "fetch_json", return_value=[public, *hidden]):
            found = catalog.discover_repositories(set())
        self.assertEqual([repo["name"] for repo in found], ["hass-a-integration"])

    def test_catalog_renders_integration_rows(self):
        items = catalog.integration_metadata(self.root / "ninebot")
        entry = {"path": "ninebot", "url": "https://github.com/seb5594/hass-demo-integration",
                 "repository": "seb5594/hass-demo-integration", "excerpt": "Demo", "commit": "b" * 40,
                 "items": items}
        readme = catalog.render_readme([entry])
        for item in ("message=1.0.0b1", "message=beta", "label=downloads", "label=integrations"):
            self.assertIn(item, readme)
        self.assertNotIn("hacs_repository.svg", readme)


if __name__ == "__main__":
    unittest.main()
