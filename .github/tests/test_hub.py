"""Hub rendering without network access."""
import unittest
from unittest.mock import patch

from support import ENGINE  # noqa: F401

import hub
import remote

GITMODULES = '[submodule "x"]\n\t# Replaced: path = .sources/Demo\n\tpath = Demo\n\turl = https://github.com/seb5594/Home-Assistant-Demo-Addon.git\n'
CONFIG = ("name: Demo App\nslug: demo\nversion: '1.2.3'\ndescription: A | piped description\n"
          "arch: [amd64, aarch64]\n")
MANIFEST = '{"domain": "demo", "name": "Demo Integration", "version": "0.4.0"}'


def fake_fetch_json(url):
    if "/contents/" in url:
        return {"sha": "a" * 40}
    if "/git/trees/" in url:
        if "Addon" in url:
            return {"tree": [{"type": "blob", "path": "demo/config.yaml"},
                             {"type": "blob", "path": ".github/config.yaml"},
                             {"type": "tree", "path": "demo"}]}
        return {"tree": [{"type": "blob", "path": "custom_components/demo/manifest.json"},
                         {"type": "blob", "path": "hacs.json"}, {"type": "blob", "path": "README.md"}]}
    raise AssertionError(url)


def fake_fetch_text(url):
    if url.endswith("/.github/catalog.json"):
        raise RuntimeError("HTTP 404")
    if url.endswith("/README.md"):
        return "# Demo\n\n[![badge](x)](y)\n\nThis is a custom component for demos.\n\nMore text.\n"
    if url.endswith("/.gitmodules"):
        if "Home-Assistant-Apps" in url:
            return GITMODULES
        return GITMODULES.replace("Home-Assistant-Demo-Addon", "hass-demo-integration")
    if url.endswith("config.yaml"):
        assert "/.github/" not in url
        return CONFIG
    if url.endswith("manifest.json"):
        return MANIFEST
    if url.endswith("hacs.json"):
        return '{"homeassistant": "2026.9.0"}'
    raise AssertionError(url)


class HubTests(unittest.TestCase):
    def setUp(self):
        for name, fake in (("fetch_json", fake_fetch_json), ("fetch_text", fake_fetch_text)):
            patcher = patch.object(remote, name, fake)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_projects_come_from_catalog_pins(self):
        self.assertEqual(hub.listed_projects(hub.CATALOGS["apps"]),
                         [("seb5594/Home-Assistant-Demo-Addon", "a" * 40)])

    def test_catalog_json_is_preferred_over_gitmodules(self):
        listing = '[{"repository": "seb5594/hass-x-integration", "commit": "' + "c" * 40 + '"}]'
        original = fake_fetch_text

        def with_listing(url):
            return listing if url.endswith("/.github/catalog.json") else original(url)
        with patch.object(remote, "fetch_text", with_listing):
            self.assertEqual(hub.listed_projects(hub.CATALOGS["integrations"]),
                             [("seb5594/hass-x-integration", "c" * 40)])

    def test_integration_description_falls_back_to_the_readme_intro(self):
        entry = hub.collect("integrations")[0]
        self.assertEqual(entry["items"][0]["description"], "This is a custom component for demos.")

    def test_hidden_config_folders_are_ignored(self):
        apps = hub.collect("apps")
        self.assertEqual([app["slug"] for entry in apps for app in entry["items"]], ["demo"])

    def test_readme_merges_both_catalogs(self):
        readme = hub.render_readme(hub.collect("apps"), hub.collect("integrations"))
        for item in ("Demo App", "Demo Integration", "message=1.2.3", "message=0.4.0", "amd64 · aarch64",
                     "≥ 2026.9.0", "A \\| piped description", "label=apps&message=1", "label=integrations&message=1"):
            self.assertIn(item, readme)
        self.assertNotIn("{{", readme)

    def test_title_without_description_has_no_empty_line_break(self):
        self.assertEqual(hub.title_cell("Demo", "https://x", ""), "**[Demo](https://x)**")
        self.assertEqual(hub.title_cell("Demo", "https://x", "Text"), "**[Demo](https://x)**<br>Text")

    def test_missing_catalog_file_means_empty_catalog(self):
        def failing(url):
            raise RuntimeError("HTTP 404")
        with patch.object(remote, "fetch_text", failing):
            self.assertEqual(hub.listed_projects(hub.CATALOGS["apps"]), [])


if __name__ == "__main__":
    unittest.main()
