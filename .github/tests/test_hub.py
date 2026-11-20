"""Hub rendering without network access."""
import unittest
from unittest.mock import patch

from support import ENGINE  # noqa: F401

import excerpt
import hub
import live
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


class ExcerptTests(unittest.TestCase):
    def test_navigation_lines_are_not_a_description(self):
        text = "# T\n\n**Changelog** · **[Download](https://x)**\n\nThis is a custom component.\n"
        self.assertEqual(excerpt.first_paragraph(text), "This is a custom component.")

    def test_prose_with_bold_words_is_kept(self):
        self.assertEqual(excerpt.first_paragraph("A **fast** loopback."), "A **fast** loopback.")


class HubTests(unittest.TestCase):
    def setUp(self):
        facts = patch.object(live, "fetch", return_value={
            "stars": 0, "forks": 0, "issues": 0, "releases": 0, "downloads": 0,
            "builds": 0})
        facts.start()
        self.addCleanup(facts.stop)
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
                     "≥ 2026.9.0", "A \\| piped description", "label=apps&amp;message=1", "label=integrations&amp;message=1"):
            self.assertIn(item, readme)
        self.assertNotIn("{{", readme)

    def test_status_badges_with_values_render_as_markdown(self):
        with patch.object(live, "fetch", return_value={"builds": 1, "stars": 2, "releases": 1}):
            readme = hub.render_readme(hub.collect("apps"), hub.collect("integrations"))
        for label in ("build", "stars", "checks", "downloads"):
            self.assertIn(f"[![{label}]", readme)

    def test_status_badges_without_values_are_hidden(self):
        readme = hub.render_readme(hub.collect("apps"), hub.collect("integrations"), own=dict(live.fetch()))
        for hidden in ("label=build", "label=stars", "label=downloads", "label=hub%20sync"):
            self.assertNotIn(hidden, readme)
        self.assertIn("label=version", readme)

    def test_thanks_and_license_close_the_page(self):
        readme = hub.render_readme(hub.collect("apps"), hub.collect("integrations"))
        self.assertLess(readme.index("## How this works"), readme.index("## Say thanks"))
        self.assertLess(readme.index("## Say thanks"), readme.index("## License"))
        self.assertTrue(readme.rstrip().endswith("terms apply."))

    def test_a_description_that_repeats_the_name_is_left_out(self):
        self.assertEqual(hub.title_cell("Car Tires Season", "https://x", "car tires season"), "**[Car Tires Season](https://x)**")

    def test_icons_come_from_the_pinned_commit_and_are_optional(self):
        entry = {"repository": "seb5594/hass-demo-integration", "sha": "a" * 40}
        self.assertEqual(hub.icon_cell(entry, {}), "")
        cell = hub.icon_cell(entry, {"icon": "custom_components/demo/brand/icon.png"})
        self.assertIn(f"seb5594/hass-demo-integration/{'a' * 40}/custom_components/demo/brand/icon.png", cell)

    def test_the_header_puts_logo_and_title_into_one_heading(self):
        readme = hub.render_readme(hub.collect("apps"), hub.collect("integrations"))
        self.assertTrue(readme.startswith('<h1 align="center">'))
        self.assertEqual(readme.count("<h1"), 1)
        self.assertLess(readme.index("<img src="), readme.index("Home Assistant Hub"))

    def test_pulls_and_downloads_are_summed_under_their_tables(self):
        apps = [{"items": [{"metrics": {"image_pulls": 120}}, {"metrics": {}}, {}]},
                {"items": [{"metrics": {"image_pulls": 30}}]}]
        self.assertEqual(hub.app_pulls(apps), 150)
        integrations = [{"live": {"downloads": 1985}}, {"live": None}, {}]
        self.assertEqual(hub.integration_downloads(integrations), 1985)
        self.assertEqual(hub.total_line("Total image pulls", 1500, 4, "apps"), "**Total image pulls:** 1,500 across 4 apps.")
        self.assertEqual(hub.total_line("Total image pulls", 0, 4, "apps"), "")

    def test_an_app_with_measured_pulls_shows_them_in_its_status(self):
        entries = hub.collect("apps")
        entries[0]["items"][0]["metrics"] = {"image_pulls": 1234}
        self.assertIn("label=pulls&message=1.2k", hub.app_table(entries))

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
