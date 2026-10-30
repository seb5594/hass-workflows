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
        facts = patch.object(catalog.live, "fetch", return_value={
            "stars": 1, "forks": 0, "issues": 0, "releases": 1, "downloads": 0,
            "builds": 1})
        facts.start()
        self.addCleanup(facts.stop)
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
        for item in ("message=1.74.1", "label=mounts%20%28read-only%29", "label=local%20disks", "Pinned commit",
                     "label=apps"):
            self.assertIn(item, readme)
        self.assertNotIn("{{", readme)
        self.assertNotIn("buymeacoffee", readme.split("## Available apps")[1].split("## Support")[0])

    def test_repository_metadata_names_the_maintainer_handle(self):
        self.assertIn("maintainer: seb5594", catalog.repository_yaml())

    def test_plural_bundle_discovery_excludes_catalog_and_private_sources(self):
        public = {"name": "Home-Assistant-Anti-Tuya-Apps", "owner": {"login": "seb5594"}}
        with patch.object(catalog.github_api, "fetch_json", return_value=[public,
                {**public, "name": "Home-Assistant-Apps"},
                {**public, "name": "Home-Assistant-Secret-Apps", "private": True}]):
            self.assertEqual(catalog.discover_repositories(set()), [public])
        self.assertEqual(catalog.project_path(public['name']), 'Anti-Tuya')

    def test_bundle_has_three_distinct_documented_entries_on_its_actual_branch(self):
        for slug, name in [('tuya_breaker', 'Tuya Breaker'), ('untuyaos3_wifi', 'Anti Tuya WiFi Helper')]:
            app = self.source / slug
            app.mkdir()
            (app / 'config.yaml').write_text(f'name: {name}\nversion: "1.1.0-beta.2"\nslug: {slug}\n'
                                            f'description: About {name}\narch: [amd64, aarch64]\n')
            (app / 'README.md').write_text(f'# {name}\n\nSetup instructions for {name}.\n')
        entry = {'path': 'Anti-Tuya', 'url': 'https://github.com/seb5594/Home-Assistant-Anti-Tuya-Apps',
                 'repository': 'seb5594/Home-Assistant-Anti-Tuya-Apps', 'branch': 'dev',
                 'excerpt': 'Do not use this bundle-wide introduction.', 'commit': 'a'*40,
                 'metrics':{'image_size':{'amd64':999999999},'runtime_tests':999},
                 'live':{'builds':1}, 'items': catalog.app_metadata(self.source)}
        rendered = catalog.render_catalog([entry])
        self.assertEqual(rendered.count('### ['), 3)
        self.assertEqual(rendered.count('[README & setup]'), 3)
        self.assertIn('Setup instructions for Anti Tuya WiFi Helper.', rendered)
        self.assertIn('/blob/dev/tuya_breaker/CHANGELOG.md', rendered)
        self.assertIn('/tree/' + 'a'*40 + '/untuyaos3_wifi', rendered)
        self.assertNotIn('bundle-wide introduction', rendered)
        self.assertIn('branch=dev',rendered)
        self.assertNotIn('999',rendered)


class IntegrationCatalog(unittest.TestCase):
    def setUp(self):
        for name, value in (("KIND", "integrations"), ("NAME_PATTERN", catalog.re.compile(
                catalog.NAME_PATTERNS["integrations"])),
                            ("TEMPLATES", catalog.ENGINE / ".templates/catalog/integrations"),
                            ("CATALOG_REPOSITORY", "seb5594/Home-Assistant-Integrations")):
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
        with patch.object(catalog.github_api, "fetch_json", return_value=[public, *hidden]):
            found = catalog.discover_repositories(set())
        self.assertEqual([repo["name"] for repo in found], ["hass-a-integration"])

    FACTS = {"license": "", "stars": 0, "forks": 0, "issues": 0, "releases": 0, "downloads": 0,
             "builds": 0}

    def describe(self, **facts):
        repo = {"name": "hass-demo-integration", "default_branch": "main"}
        manifest = '{"domain": "demo", "name": "Demo", "version": "1.0.0b1", "iot_class": "local_polling"}'
        with patch.object(catalog.remote, "head_commit", return_value="b" * 40), \
                patch.object(catalog.remote, "project_files", return_value=[
                    "custom_components/demo/manifest.json", "hacs.json", "README.md"]), \
                patch.object(catalog.remote, "raw", side_effect=lambda r, s, path: {
                    "custom_components/demo/manifest.json": manifest, "hacs.json": '{"homeassistant": "2026.9.0"}',
                    "README.md": "# Demo\n\nThis is a custom component for demos.\n"}[path]), \
                patch.object(catalog.live, "fetch", return_value={**self.FACTS, **facts}):
            return catalog.describe_repository(repo, 500)

    def test_description_comes_from_the_readme_and_nothing_is_cloned(self):
        entry = self.describe()
        self.assertEqual(entry["excerpt"], "This is a custom component for demos.")
        self.assertEqual(entry["items"][0]["description"], entry["excerpt"])
        self.assertEqual(entry["commit"], "b" * 40)

    def test_entry_shows_the_version_in_the_heading_and_only_a_changelog_link(self):
        readme = catalog.render_readme([self.describe()], own=dict(self.FACTS))
        self.assertIn("### [demo](https://github.com/seb5594/hass-demo-integration) (1.0.0b1)", readme)
        self.assertIn("> This is a custom component for demos.\n\n[Changelog](", readme)
        self.assertNotIn("**Demo**", readme)

    def test_support_section_and_license_note(self):
        unlicensed = catalog.render_readme([self.describe()], own=dict(self.FACTS))
        licensed = catalog.render_readme([self.describe(license="Apache-2.0")], own=dict(self.FACTS))
        self.assertIn("## Say thanks", unlicensed)
        self.assertIn("style=for-the-badge", unlicensed)
        self.assertIn("## Support", unlicensed)
        self.assertNotIn("## License", unlicensed)
        self.assertTrue(licensed.rstrip().endswith("terms apply."))
        self.assertLess(licensed.index("## Say thanks"), licensed.index("## License"))
        self.assertNotIn("label=license", licensed)

    def test_entries_without_values_hide_their_badges(self):
        quiet = catalog.render_readme([self.describe()], own=dict(self.FACTS))
        busy = catalog.render_readme([self.describe(stars=2, forks=1, releases=1, downloads=3, builds=1)], own={
            **self.FACTS, "stars": 5, "forks": 1, "builds": 2})
        for hidden in ("label=stars", "label=forks", "label=downloads", "label=catalog%20sync"):
            self.assertNotIn(hidden, quiet)
        for shown in ("label=stars", "label=forks", "label=downloads", "label=catalog%20sync"):
            self.assertIn(shown, busy)
        self.assertIn("message=%E2%89%A5%202026.9.0", quiet)


if __name__ == "__main__":
    unittest.main()
