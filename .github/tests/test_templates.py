"""Protect project discovery, the README header with its three badge sizes, and the closing blocks."""
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

import support  # noqa: F401

import badgekit
import project
import projectmeta
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


def make_integration(root, hacs=None, **manifest):
    folder = root / "custom_components/demo"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps({
        "domain": "demo", "name": "Demo Integration", "version": "1.2.3b1", "config_flow": True,
        "documentation": "https://github.com/seb5594/demo-integration", **manifest}))
    (root / "hacs.json").write_text(json.dumps({"homeassistant": "2026.9.0"} if hacs is None else hacs))
    return folder


def paragraphs(header):
    """The centered paragraphs of a header, one per badge row."""
    return re.findall(r'<p align="center">\n(.*?)\n</p>', header, re.S)


class ProjectDiscovery(unittest.TestCase):
    def test_app_is_found_by_its_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = make_app(root)
            found = projectmeta.discover(root)
            self.assertEqual((found.kind, found.folder, found.version, found.slug),
                             ("app", app, "2.3.4", "sample"))
            self.assertEqual(found.repository, "seb5594/Home-Assistant-Sample-Addon")

    def test_integration_is_found_by_its_manifest_and_hacs_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_integration(root)
            found = projectmeta.discover(root)
            self.assertEqual((found.kind, found.slug, found.name), ("integration", "demo", "Demo Integration"))
            self.assertEqual(found.hacs["homeassistant"], "2026.9.0")
            self.assertEqual(found.repository, "seb5594/demo-integration")

    def test_ambiguous_projects_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("app-a", "app-b"):
                (root / name).mkdir()
                (root / name / "config.yaml").write_text("slug: example\n")
            with self.assertRaisesRegex(ValueError, "exactly one"):
                projectmeta.discover(root)


class HeaderStructure(unittest.TestCase):
    """Name, logo, separator, then the badge rows from the largest to the smallest."""

    def header(self, **options):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_integration(root, **options)
            return readme.header(root)

    def test_name_is_centered_and_followed_by_a_separator(self):
        block = self.header()
        self.assertTrue(block.startswith(readme.START + '\n<h1 align="center">Demo Integration</h1>'))
        self.assertTrue(block.endswith(readme.END))
        self.assertLess(block.index("<h1"), block.index("\n---\n"))
        self.assertLess(block.index("\n---\n"), block.index("label=Support"))

    def test_rows_shrink_from_support_to_the_plain_facts(self):
        rows = paragraphs(self.header())
        self.assertEqual(len(rows), 3)
        heights = [set(re.findall(r'height="(\d+)"', row)) for row in rows]
        self.assertEqual(heights, [{"40"}, {"28"}, {"20"}])
        self.assertEqual(badgekit.HERO.height, 2 * badgekit.MINOR.height)
        self.assertIn("style=for-the-badge", rows[0])
        self.assertIn("style=for-the-badge", rows[1])
        self.assertIn("style=flat", rows[2])

    def test_support_row_links_paypal_me_and_coffee(self):
        support_row = paragraphs(self.header())[0]
        self.assertIn('href="https://paypal.me/seb5594"', support_row)
        self.assertIn('href="https://buymeacoffee.com/seb5594"', support_row)
        self.assertLess(support_row.index("PayPal"), support_row.index("Buy%20Me%20a%20Coffee"))

    def test_middle_row_lists_hacs_minimum_version_release_and_downloads(self):
        row = paragraphs(self.header())[1]
        labels = re.findall(r"label=([^&]+)", row)
        self.assertEqual(labels, ["HACS", "home%20assistant", "version", "downloads"])
        self.assertIn("message=%E2%89%A5%202026.9.0", row)
        self.assertIn("owner=seb5594&amp;repository=demo-integration&amp;category=integration", row)

    def test_without_a_minimum_version_that_badge_is_omitted(self):
        row = paragraphs(self.header(hacs={}))[1]
        self.assertNotIn("home%20assistant", row)

    def test_offline_rendering_keeps_the_unconditional_badges(self):
        row = paragraphs(self.header())[2]
        for kept in ("label=stars", "label=issues", "label=checks"):
            self.assertIn(kept, row)
        self.assertNotIn("label=tests", row)
        self.assertNotIn("label=license", row)


class HeaderLogo(unittest.TestCase):
    @staticmethod
    def png(path, width, height):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x89PNG\r\n\x1a\n" + (13).to_bytes(4, "big") + b"IHDR"
                         + width.to_bytes(4, "big") + height.to_bytes(4, "big"))

    def block(self, prepare):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = make_integration(root)
            prepare(folder / "brand")
            return readme.header(root)

    def test_logo_is_preferred_over_icon(self):
        def prepare(brand):
            self.png(brand / "logo.png", 200, 100)
            self.png(brand / "icon.png", 256, 256)
        block = self.block(prepare)
        self.assertIn("brand/logo.png", block)
        self.assertNotIn("brand/icon.png", block)
        self.assertIn('width="200" height="100"', block)

    def test_icon_is_the_fallback(self):
        block = self.block(lambda brand: self.png(brand / "icon.png", 128, 128))
        self.assertIn("raw.githubusercontent.com/seb5594/demo-integration/main/custom_components/demo/brand/icon.png", block)

    def test_no_picture_leaves_the_space_empty(self):
        block = self.block(lambda brand: None)
        self.assertNotIn("raw.githubusercontent.com", block)
        self.assertNotIn("<picture>", block)
        self.assertEqual(block.count("\n\n\n"), 0)

    def test_sharp_and_dark_variants_are_used_and_large_logos_scaled_down(self):
        def prepare(brand):
            self.png(brand / "logo.png", 394, 256)
            self.png(brand / "logo@2x.png", 788, 512)
            self.png(brand / "dark_logo@2x.png", 788, 512)
        block = self.block(prepare)
        self.assertIn("brand/logo@2x.png", block)
        self.assertIn('media="(prefers-color-scheme: dark)"', block)
        self.assertIn("brand/dark_logo@2x.png", block)
        self.assertIn('width="246" height="160"', block)

    def test_app_logo_sits_in_the_app_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = make_app(root)
            self.png(app / "logo.png", 300, 100)
            self.assertIn("main/sample/logo.png", readme.header(root))


class HeaderBadges(unittest.TestCase):
    EMPTY = {"license": "", "stars": 0, "forks": 0, "issues": 0, "releases": 0, "latest_tag": "",
             "downloads": 0, "builds": 0}
    MEASURED = {"tests": 202}

    def rows(self, measured=None, compat=False, **facts):
        manifest = {"domain": "demo", "version": "1.0.0", "config_flow": True}
        rows = badgekit.integration_rows(manifest, {"homeassistant": "2026.9.0"}, "seb5594/demo",
                                         live={**self.EMPTY, **facts}, measured_values=measured, compat=compat)
        return badgekit.render(badgekit.plain(rows))

    def test_conditional_badges_are_hidden_without_a_value(self):
        block = self.rows()
        for hidden in ("label=stars", "label=downloads", "label=checks", "label=tests", "label=license"):
            self.assertNotIn(hidden, block)
        for kept in ("label=version", "label=issues", "label=home%20assistant"):
            self.assertIn(kept, block)

    def test_issues_are_shown_even_at_zero(self):
        self.assertIn("github/issues/seb5594/demo", self.rows(issues=0))

    def test_conditional_badges_appear_with_a_value(self):
        block = self.rows(self.MEASURED, True, stars=3, license="MIT", releases=2, builds=4,
                          latest_tag="v1.0.0b3", downloads=7)
        for shown in ("label=stars", "label=license", "label=checks", "label=tests&message=202%20passed",
                      "compat.yml"):
            self.assertIn(shown, block)

    def test_version_and_downloads_follow_the_latest_release(self):
        block = self.rows(releases=2, latest_tag="v1.0.0b3")
        self.assertIn("message=1.0.0b3", block)
        self.assertIn("/releases/tag/v1.0.0b3", block)
        self.assertIn("github/downloads/seb5594/demo/v1.0.0b3/total", block)

    def test_version_falls_back_to_the_metadata_before_the_first_release(self):
        block = self.rows()
        self.assertIn("message=1.0.0", block)
        self.assertNotIn("label=downloads", block)

    def test_downloads_count_from_the_first_release_even_at_zero(self):
        self.assertIn("label=downloads", self.rows(releases=1, latest_tag="v1.0.0", downloads=0))

    def test_noassertion_is_not_a_license(self):
        self.assertNotIn("label=license", self.rows(license="NOASSERTION"))


class AppHeader(unittest.TestCase):
    def test_app_rows_follow_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_app(root)
            block = readme.header(root)
            for item in ("message=2.3.4", "message=amd64%20%C2%B7%20armv7", "label=mounts",
                         "message=config%20%C2%B7%20share%20%28rw%29", "message=enabled"):
                self.assertIn(item, block)
            self.assertNotIn("i386", block)
            for removed in ("label=startup", "label=boot", "label=supervisor", "label=base"):
                self.assertNotIn(removed, block)
            self.assertIn("message=2", block)  # leaf option count, not group count

    def test_app_rows_share_the_integration_tiers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_app(root)
            rows = paragraphs(readme.header(root))
            heights = [set(re.findall(r'height="(\d+)"', row)) for row in rows]
            self.assertEqual(heights, [{"40"}, {"28"}, {"20"}, {"20"}])
            self.assertIn("supervisor_add_addon_repository", rows[1])
            self.assertIn("label=arch", rows[3])

    def test_measurements_come_from_the_committed_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_app(root)
            (root / ".github").mkdir()
            (root / ".github/metrics.json").write_text(json.dumps({
                "image_pulls": 1234, "runtime_tests": 12,
                "image_size": {"armv7": 12 * 1024 * 1024, "amd64": 16 * 1024 * 1024}}))
            block = readme.header(root)
            self.assertIn("label=image%20pulls&amp;message=1.2k", block)
            self.assertIn("message=amd64%2016.0%20%C2%B7%20armv7%2012.0%20MiB", block)
            self.assertIn("label=runtime%20tests&amp;message=12%20passed", block)

    def test_catalog_listings_leave_out_support_and_install(self):
        rows = badgekit.app_rows({"version": "1", "arch": ["amd64"]}, "o/n", standalone=False)
        text = badgekit.render(badgekit.plain(rows))
        self.assertNotIn("label=Support", text)
        self.assertNotIn("supervisor_add_addon_repository", text)
        self.assertIn("label=arch", text)


class BadgeLayout(unittest.TestCase):
    def test_every_layout_entry_has_a_builder(self):
        for layout, builders in ((badgekit.APP_LAYOUT, badgekit._app_builders()),
                                 (badgekit.INTEGRATION_LAYOUT, badgekit._integration_builders())):
            for _, names in layout:
                for name in names:
                    self.assertIn(name, builders)

    def test_tiers_are_ordered_from_large_to_small(self):
        self.assertGreater(badgekit.HERO.height, badgekit.MAJOR.height)
        self.assertGreater(badgekit.MAJOR.height, badgekit.MINOR.height)


class ReadmeUpdates(unittest.TestCase):
    def test_update_replaces_the_old_title_logo_and_badge_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_app(root)
            (root / "README.md").write_text(
                '<p align="center">\n  <img src="logo.png" width="360">\n</p>\n\n# Sample\n\n'
                "<!-- badges:begin (generated from project metadata) -->\nold\n<!-- badges:end -->\n\n"
                "Intro text.\n")
            self.assertTrue(readme.update(root))
            text = (root / "README.md").read_text()
            self.assertTrue(text.startswith(readme.START))
            self.assertNotIn("# Sample", text)
            self.assertNotIn("badges:begin", text)
            self.assertNotIn("logo.png\" width", text)
            self.assertIn(f"{readme.END}\n\nIntro text.", text)
            self.assertFalse(readme.update(root))

    def test_update_inserts_and_checks_the_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_app(root)
            (root / "README.md").write_text("# Sample\n\nText\n")
            with self.assertRaises(ValueError):
                readme.verify(root)
            self.assertTrue(readme.update(root))
            readme.verify(root)
            self.assertFalse(readme.update(root))
            self.assertTrue((root / "README.md").read_text().startswith(readme.START))
            self.assertIn("\n\nText\n", (root / "README.md").read_text())

    def test_hand_written_text_after_the_header_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_app(root)
            (root / "README.md").write_text("# Sample\n\n[English](README.md) · [Deutsch](de.md)\n\nText.\n")
            readme.update(root)
            text = (root / "README.md").read_text()
            self.assertIn(f"{readme.END}\n\n[English](README.md)", text)

    def test_support_block_is_appended_once_with_large_badges(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_app(root)
            (root / "README.md").write_text("# Sample\n\nText\n\n## License\n\nOpen.\n")
            readme.update(root)
            text = (root / "README.md").read_text()
            self.assertEqual(text.count(readme.SUPPORT_START), 1)
            self.assertTrue(text.rstrip().endswith(readme.SUPPORT_END))
            tail = text[text.index(readme.SUPPORT_START):]
            self.assertIn("## Say thanks", tail)
            self.assertIn("hot drink", tail)
            self.assertEqual(tail.count("style=for-the-badge"), 2)
            self.assertIn("https://paypal.me/seb5594", tail)
            self.assertFalse(readme.update(root))

    def test_license_section_closes_the_readme_after_the_thanks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_app(root)
            (root / "LICENSE.md").write_text("                Apache License\n          Version 2.0, January 2004\n")
            (root / "README.md").write_text("# Sample\n\nText\n")
            readme.update(root)
            text = (root / "README.md").read_text()
            self.assertTrue(text.rstrip().endswith(readme.LICENSE_END))
            self.assertLess(text.index(readme.SUPPORT_END), text.index(readme.LICENSE_START))
            self.assertIn("[Apache License 2.0](LICENSE.md)", text)
            self.assertIn("message=Apache-2.0", text)
            # A license file makes the offline header show the license badge too.
            self.assertIn("github/license/seb5594/Home-Assistant-Sample-Addon", readme.header(root))
            self.assertFalse(readme.update(root))
            # Text written below the generated blocks is moved above them on the next refresh.
            (root / "README.md").write_text(text + "\n## Later section\n\nMore.\n")
            self.assertTrue(readme.update(root))
            moved = (root / "README.md").read_text()
            self.assertLess(moved.index("## Later section"), moved.index(readme.SUPPORT_START))
            self.assertTrue(moved.rstrip().endswith(readme.LICENSE_END))
            self.assertEqual(moved.count(readme.LICENSE_START), 1)


class ShellScriptDiscovery(unittest.TestCase):
    def test_extensionless_scripts_are_found_by_their_shebang(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "svc").mkdir()
            (root / "svc/run").write_text("#!/command/with-contenv bash\necho\n")
            (root / "svc/type").write_text("longrun\n")
            (root / "tool.sh").write_text("echo\n")
            (root / "data.json").write_text("{}")
            names = sorted(Path(path).name for path in project.shell_scripts([root, root / "missing"]))
            self.assertEqual(names, ["run", "tool.sh"])


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


if __name__ == "__main__":
    unittest.main()
