"""Dashboard projects: cards and themes found by their metadata, checked, badged, released and listed."""
import contextlib
import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import support  # noqa: F401

import badgekit
import calver
import config
import dashboard_checks
import discovery
import hub
import live
import managed
import metrics
import package_dashboard
import project
import projectmeta
import readme
import remote

CARD_HACS = {"name": "Demo Card", "filename": "demo-card.js", "render_readme": True, "homeassistant": "2026.2.0"}
PACKAGE = {"name": "demo-card", "version": "2026.11.26", "private": True,
           "repository": {"type": "git", "url": "git+https://github.com/seb5594/Home-Assistant-Demo-Card.git"},
           "scripts": {"build": "node build.mjs", "test": "node --test"}}


def make_card(root, hacs=None, package=None):
    (root / "package-lock.json").write_text("{}")
    (root / "hacs.json").write_text(json.dumps(CARD_HACS if hacs is None else hacs))
    (root / "package.json").write_text(json.dumps(PACKAGE if package is None else package))
    (root / "README.md").write_text("# Demo\n\nA demo card.\n")
    return root


def make_theme(root):
    (root / "hacs.json").write_text(json.dumps({"name": "Demo Theme", "render_readme": True}))
    (root / "package.json").write_text(json.dumps({**PACKAGE, "name": "demo-theme", "scripts": {}}))
    (root / "themes").mkdir()
    (root / "themes/demo.yaml").write_text("Demo:\n  primary-color: '#123456'\n")
    return root


class Discovery(unittest.TestCase):
    def test_a_card_is_found_by_hacs_and_package_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            found = projectmeta.discover(make_card(Path(tmp)))
        self.assertEqual((found.kind, found.category, found.name, found.slug, found.version),
                         ("dashboard", "plugin", "Demo Card", "demo-card", "2026.11.26"))
        self.assertEqual(found.repository, "seb5594/Home-Assistant-Demo-Card")

    def test_a_theme_has_no_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            found = projectmeta.discover(make_theme(Path(tmp)))
        self.assertEqual((found.kind, found.category), ("dashboard", "theme"))

    def test_an_integration_with_a_frontend_build_stays_an_integration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_card(root)
            (root / "custom_components/demo").mkdir(parents=True)
            (root / "custom_components/demo/manifest.json").write_text(
                '{"domain": "demo", "name": "Demo", "version": "1", "documentation": "https://github.com/a/b"}')
            self.assertEqual(projectmeta.discover(root).kind, "integration")

    def test_every_spelling_of_a_repository_url_is_understood(self):
        for url in ("git+https://github.com/o/n.git", "https://github.com/o/n", "github:o/n", "git@github.com:o/n.git"):
            self.assertEqual(projectmeta.repository_of(url), "o/n", url)
        self.assertEqual(projectmeta.package_repository({"repository": "o/n"}), "o/n")
        self.assertEqual(projectmeta.package_repository({"homepage": "https://github.com/o/n#readme"}), "o/n")

    def test_scoped_package_names_give_a_plain_slug(self):
        found = projectmeta.Project("dashboard", Path("."), Path("."), {"name": "@seb5594/demo-card"}, {})
        self.assertEqual(found.slug, "demo-card")


class Naming(unittest.TestCase):
    def matches(self, name):
        found = re.fullmatch(config.NAME_PATTERNS["dashboards"], name)
        return found["project"] if found else None

    def test_cards_dashboards_and_themes_are_recognised(self):
        self.assertEqual(self.matches("Home-Assistant-Config-Entry-Lovelace-Card"), "Config-Entry")
        self.assertEqual(self.matches("Home-Assistant-Clock-Card"), "Clock")
        self.assertEqual(self.matches("hass-night-theme"), "night")
        self.assertEqual(self.matches("Home-Assistant-Wall-Dashboard"), "Wall")

    def test_apps_and_integrations_are_not_dashboards(self):
        self.assertIsNone(self.matches("Home-Assistant-Git-Exporter-Addon"))
        self.assertIsNone(self.matches("hass-ninebot_e_scooters-integration"))
        self.assertIsNone(self.matches("Home-Assistant-Card"))

    def test_the_project_is_registered_for_engine_validation(self):
        self.assertIn("Home-Assistant-Config-Entry-Lovelace-Card", config.PROJECTS["dashboards"])


class Checks(unittest.TestCase):
    def problems(self, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            return dashboard_checks.problems(make_card(Path(tmp), **kwargs))

    def errors(self, **kwargs):
        return [p for p in self.problems(**kwargs) if not p.startswith(dashboard_checks.WARNING)]

    def test_a_correct_card_has_no_errors(self):
        self.assertEqual(self.errors(), [])

    def test_unknown_hacs_keys_are_rejected_because_hacs_rejects_them(self):
        self.assertIn("hacs.json: key version is not allowed", self.errors(hacs={**CARD_HACS, "version": "1"}))

    def test_filename_must_be_a_single_js_file(self):
        for filename in ("card.css", "dist/card.js"):
            self.assertTrue(any("filename" in p for p in self.errors(hacs={**CARD_HACS, "filename": filename})))

    def test_the_lock_file_must_be_committed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_card(Path(tmp))
            (root / "package-lock.json").unlink()
            self.assertTrue(any("package-lock.json" in p for p in dashboard_checks.problems(root)))

    def test_a_card_needs_a_build_script_and_a_repository(self):
        broken = {**PACKAGE, "scripts": {}, "repository": None}
        errors = self.errors(package=broken)
        self.assertTrue(any("build" in p for p in errors))
        self.assertTrue(any("repository" in p for p in errors))

    def test_the_version_must_be_semver_or_a_calendar_version(self):
        for version in ("2026.11.26", "2026.11.26.3", "1.2.3", "1.0.0-beta.1"):
            self.assertEqual(self.errors(package={**PACKAGE, "version": version}), [], version)
        self.assertTrue(self.errors(package={**PACKAGE, "version": "latest"}))

    def test_a_public_package_only_warns(self):
        problems = self.problems(package={k: v for k, v in PACKAGE.items() if k != "private"})
        self.assertTrue(any(p.startswith(dashboard_checks.WARNING) and "private" in p for p in problems))

    def test_translations_must_have_the_keys_of_english(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_card(Path(tmp))
            folder = root / "src/translations"
            folder.mkdir(parents=True)
            (folder / "en.json").write_text('{"a": "A", "b": {"c": "C"}}')
            (folder / "de.json").write_text('{"a": "A"}')
            found = dashboard_checks.problems(root)
        self.assertTrue(any("missing key b" in p for p in found))

    def test_a_theme_needs_a_mapping_of_themes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_theme(Path(tmp))
            self.assertEqual([p for p in dashboard_checks.problems(root) if "private" not in p], [])
            (root / "themes/demo.yaml").write_text("- not a mapping\n")
            self.assertTrue(any("mapping" in p for p in dashboard_checks.problems(root)))
            (root / "themes/demo.yaml").unlink()
            self.assertTrue(any("at least one" in p for p in dashboard_checks.problems(root)))


class Badges(unittest.TestCase):
    def rows(self, hacs=None, **options):
        return badgekit.dashboard_rows(PACKAGE, CARD_HACS if hacs is None else hacs,
                                       "seb5594/Home-Assistant-Demo-Card", **options)

    def text(self, rows):
        return " ".join(str(badge) for row in rows for badge in row.badges)

    def test_the_install_badge_opens_hacs_in_the_card_category(self):
        text = self.text(self.rows())
        self.assertIn("category=plugin", text)
        self.assertIn("Add%20card", text)

    def test_a_theme_is_installed_as_a_theme(self):
        text = self.text(self.rows(hacs={"name": "T"}))
        self.assertIn("category=theme", text)
        self.assertIn("Add%20theme", text)

    def test_the_bundle_size_is_shown_once_it_was_measured(self):
        self.assertNotIn("bundle", self.text(self.rows()))
        self.assertIn("bundle%20size", self.text(self.rows(measured_values={"bundle_size": 51200})))
        self.assertIn("50.0%20KiB", self.text(self.rows(measured_values={"bundle_size": 51200})))

    def test_the_minimum_home_assistant_version_comes_from_hacs_json(self):
        self.assertIn("2026.2.0", self.text(self.rows()))

    def test_sizes_follow_the_shared_layout(self):
        self.assertEqual([row.tier for row in self.rows()],
                         [tier for tier, _ in badgekit.DASHBOARD_LAYOUT])

    def test_metrics_know_how_to_display_the_bundle_size(self):
        self.assertEqual(metrics.display("bundle_size", 2048), "2.0 KiB")


class ReadmeHeader(unittest.TestCase):
    def test_the_header_names_the_card_and_uses_its_brand_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_card(Path(tmp))
            (root / "brand").mkdir()
            png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (512).to_bytes(4, "big") * 2
            (root / "brand/icon.png").write_bytes(png)
            header = readme.header(root)
        self.assertIn("Demo Card", header)
        self.assertIn("seb5594/Home-Assistant-Demo-Card/main/brand/icon.png", header)
        self.assertIn("Add%20card", header)


class Pipeline(unittest.TestCase):
    def inspect(self, root, **env):
        buffer = io.StringIO()
        previous = Path.cwd()
        os.chdir(root)
        try:
            with patch.dict(os.environ, env, clear=False), contextlib.redirect_stdout(buffer):
                project.main("inspect")
        finally:
            os.chdir(previous)
        return dict(line.split("=", 1) for line in buffer.getvalue().splitlines() if "=" in line)

    def test_inspect_describes_a_card_and_releases_from_the_default_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            facts = self.inspect(make_card(Path(tmp)), PUBLISH="true", EVENT_NAME="push", DEFAULT_BRANCH="main",
                                 REF="refs/heads/main", GITHUB_REPOSITORY="seb5594/Home-Assistant-Demo-Card")
        self.assertEqual((facts["kind"], facts["category"], facts["images"], facts["release"]),
                         ("dashboard", "plugin", "false", "true"))

    def test_pull_requests_never_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            facts = self.inspect(make_card(Path(tmp)), PUBLISH="true", EVENT_NAME="pull_request",
                                 DEFAULT_BRANCH="main", REF="refs/pull/1/merge")
        self.assertEqual(facts["release"], "false")

    def test_the_test_count_is_read_from_node_output(self):
        for output, count in (("ℹ tests 14\nℹ pass 12\nℹ fail 0", "12"), ("# tests 3\n# pass 3\n", "3")):
            self.assertEqual(project.TESTS_PASSED.search(output)[1], count)

    def test_a_missing_bundle_fails_with_the_file_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            card = projectmeta.discover(make_card(Path(tmp)))
            previous = Path.cwd()
            os.chdir(tmp)
            try:
                with patch.object(package_dashboard, "run"), self.assertRaisesRegex(AssertionError, "demo-card.js"):
                    package_dashboard.build(card)
            finally:
                os.chdir(previous)

    def test_a_release_without_a_catalog_wakes_the_hub(self):
        self.assertEqual(package_dashboard.notification_target(), (config.EVENTS["hub"], config.HUB_REPOSITORY))
        with patch.object(config, "UNCATALOGUED", set()):
            self.assertEqual(package_dashboard.notification_target(),
                             (config.EVENTS["dashboards"], config.DASHBOARDS_CATALOG))

    def test_the_release_carries_only_the_js_file(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "demo-card.js").write_text("console.log(1)")
            (out / "other.zip").write_text("x")
            with patch.object(package_dashboard.package_integration, "gh_json", return_value=None), \
                    patch.object(package_dashboard.package_integration, "generated_notes", return_value="notes"), \
                    patch.object(package_dashboard.package_integration, "run", lambda *a, **k: calls.append(a)), \
                    patch.dict(os.environ, {"GITHUB_REPOSITORY": "o/r", "GITHUB_SHA": "a" * 40}):
                package_dashboard.package_integration.publish("2026.11.26", {"version": "2026.11.26"}, CARD_HACS, out, "*.js")
        args = [str(arg) for arg in calls[0]]
        self.assertIn(str(out / "demo-card.js"), args)
        self.assertNotIn(str(out / "other.zip"), args)
        self.assertIn("2026.11.26", args)


class Managed(unittest.TestCase):
    def test_the_caller_reacts_to_calendar_tags(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = managed.expected("dashboard", "a" * 40, make_card(Path(tmp)))
        caller = files[".github/workflows/ci.yml"]
        self.assertIn("tags: ['[0-9]*']", caller)
        self.assertIn("ref: " + "a" * 40, caller)
        for shared in (".github/renovate.json", ".github/dependabot.yml", ".github/FUNDING.yml"):
            self.assertIn(shared, files)

    def test_semver_cards_keep_the_v_tags(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_card(Path(tmp), package={**PACKAGE, "version": "1.2.3"})
            files = managed.expected("dashboard", "a" * 40, root)
        self.assertIn("tags: ['v*']", files[".github/workflows/ci.yml"])

    def test_a_card_gets_no_integration_only_workflows(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = managed.expected("dashboard", "a" * 40, make_card(Path(tmp)))
        self.assertEqual(sorted(path for path in files if "workflows" in path), [".github/workflows/ci.yml"])

    def test_the_dashboard_catalog_has_its_own_caller_and_notes(self):
        files = managed.expected("catalog-dashboards", "a" * 40)
        self.assertIn("kind: dashboards", files[".github/workflows/update.yml"])
        self.assertIn("update-dashboards", files[".github/workflows/update.yml"])
        self.assertIn("Home-Assistant-<project>-Card", files[".github/DEVELOPMENT.md"])


class Calver(unittest.TestCase):
    def test_the_version_in_package_json_is_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_card(Path(tmp))
            changed = calver.bump(root, "2026.11.26")
            self.assertEqual(list(changed.values()), ["2026.11.26.1"])
            self.assertEqual(json.loads((root / "package.json").read_text())["version"], "2026.11.26.1")


CATALOG_TREE = {"tree": [{"type": "blob", "path": "hacs.json"}, {"type": "blob", "path": "package.json"},
                         {"type": "blob", "path": "README.md"}, {"type": "blob", "path": "brand/icon@2x.png"}]}


def fake_fetch_json(url):
    if "/git/trees/" in url:
        return CATALOG_TREE
    if url.endswith("/commits/main"):
        return {"sha": "b" * 40}
    raise AssertionError(url)


def fake_fetch_text(url):
    if url.endswith("/.github/catalog.json") or url.endswith("/.gitmodules"):
        raise RuntimeError("HTTP 404")
    if url.endswith("hacs.json"):
        return json.dumps(CARD_HACS)
    if url.endswith("package.json"):
        return json.dumps({**PACKAGE, "description": "Shows config entries."})
    if url.endswith("README.md"):
        return "# Demo\n\nA demo card.\n"
    raise AssertionError(url)


class Listing(unittest.TestCase):
    def setUp(self):
        for target, name, fake in ((remote, "fetch_json", fake_fetch_json), (remote, "fetch_text", fake_fetch_text),
                                   (live, "fetch", lambda *a, **k: {"stars": 0, "forks": 0, "issues": 0,
                                                                    "releases": 1, "downloads": 7, "builds": 1,
                                                                    "latest_tag": "2026.11.26"})):
            patcher = patch.object(target, name, fake)
            patcher.start()
            self.addCleanup(patcher.stop)
        repositories = [{"name": "Home-Assistant-Demo-Card", "default_branch": "main"}]
        patcher = patch.object(discovery, "public_repositories", return_value=repositories)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_remote_loader_shapes_a_card_like_a_manifest(self):
        item = remote.load_dashboards("o/r", "a" * 40, ["hacs.json", "package.json", "brand/icon@2x.png"])[0]
        self.assertEqual((item["name"], item["slug"], item["category"], item["version"], item["icon"]),
                         ("Demo Card", "demo-card", "plugin", "2026.11.26", "brand/icon@2x.png"))

    def test_a_repository_without_the_metadata_lists_nothing(self):
        self.assertEqual(remote.load_dashboards("o/r", "a" * 40, ["README.md"]), [])

    def test_the_hub_reads_dashboards_directly_while_they_have_no_catalog(self):
        self.assertEqual(hub.projects_of("dashboards"), [("seb5594/Home-Assistant-Demo-Card", "b" * 40)])

    def test_the_hub_prefers_a_catalog_once_it_exists(self):
        listing = '[{"repository": "seb5594/Home-Assistant-Other-Card", "commit": "' + "c" * 40 + '"}]'
        original = fake_fetch_text
        with patch.object(remote, "fetch_text", lambda url: listing if url.endswith("/.github/catalog.json")
                          and "Dashboards" in url else original(url)):
            self.assertEqual(hub.projects_of("dashboards"), [("seb5594/Home-Assistant-Other-Card", "c" * 40)])

    def test_apps_and_integrations_never_fall_back_to_discovery(self):
        self.assertNotIn("apps", config.UNCATALOGUED)
        self.assertNotIn("integrations", config.UNCATALOGUED)

    def test_the_hub_lists_the_card_in_its_own_section(self):
        dashboards = hub.collect("dashboards")
        apps = [{"repository": "o/a", "sha": "a" * 40, "live": {}, "items": [
            {"name": "App", "slug": "app", "version": "1", "arch": ["amd64"], "description": "x"}]}]
        text = hub.render_readme(apps, [], dashboards)
        self.assertIn("## Dashboards", text)
        self.assertIn("Demo Card", text)
        self.assertIn("| Card |", text)
        self.assertIn("label=dashboards&amp;message=1", text)
        self.assertIn('<a href="#dashboards">Dashboards</a>', text)
        self.assertNotIn("{{", text)
        self.assertLess(text.index("## Integrations"), text.index("## Dashboards"))
        self.assertLess(text.index("## Dashboards"), text.index("## How this works"))

    def test_an_empty_dashboard_section_says_so(self):
        text = hub.render_readme([{"repository": "o/a", "sha": "a" * 40, "live": {}, "items": [
            {"name": "App", "slug": "app", "version": "1", "arch": ["amd64"], "description": "x"}]}], [], [])
        self.assertIn("_No dashboards are published yet._", text)


def make_integration_with_frontend(root):
    from test_templates import make_integration
    folder = make_integration(root)
    (root / "frontend").mkdir()
    (root / "frontend/package.json").write_text(json.dumps({"name": "panel", "scripts": {"build": "x", "test": "y"}}))
    return folder


class IntegrationFrontend(unittest.TestCase):
    """An integration may ship a card of its own: frontend/ is built into the component folder."""

    def test_the_frontend_folder_is_found_by_its_package_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertIsNone(project.frontend_directory(root))
            make_integration_with_frontend(root)
            self.assertEqual(project.frontend_directory(root), root / "frontend")

    def test_it_stays_an_integration_and_inspect_tells_the_action_to_set_up_node(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_integration_with_frontend(Path(tmp))
            facts = Pipeline().inspect(tmp, PUBLISH="true", EVENT_NAME="push", DEFAULT_BRANCH="main", REF="refs/heads/main")
        self.assertEqual((facts["kind"], facts["frontend"]), ("integration", "true"))

    def test_without_a_frontend_inspect_says_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            from test_templates import make_integration
            make_integration(Path(tmp))
            self.assertEqual(Pipeline().inspect(tmp)["frontend"], "false")

    def test_node_tests_add_to_the_python_test_count(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(metrics, "RUN_STORE", Path(tmp) / "m.json"):
            frontend = Path(tmp) / "frontend"
            frontend.mkdir()
            (frontend / "package.json").write_text(json.dumps({"scripts": {"test": "x"}}))
            metrics.record("tests", 10)
            calls = []
            with patch.object(project, "run", lambda *a, **k: calls.append((a, k.get("cwd")))), \
                    patch.object(project, "run_captured", return_value="ℹ pass 7\n"):
                project.run_node_checks(frontend)
            self.assertEqual(metrics.recorded()["tests"], 17)
        self.assertEqual(calls[0][0][:2], ("npm", "ci"))
        self.assertEqual(calls[0][1], frontend)

    def test_the_build_must_write_into_the_component_folder_and_its_size_is_recorded(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(metrics, "RUN_STORE", Path(tmp) / "m.json"):
            root = Path(tmp)
            folder = make_integration_with_frontend(root)
            card = projectmeta.discover(root)
            with patch.object(project, "run"), self.assertRaisesRegex(AssertionError, "must write"):
                project.build_frontend(card)
            (folder / "frontend").mkdir()
            (folder / "frontend/panel.js").write_text("x" * 100)
            with patch.object(project, "run") as runner:
                built = project.build_frontend(card, rebuild=False)
            runner.assert_not_called()  # a finished build is reused by the release step
            self.assertEqual([path.name for path in built], ["panel.js"])
            self.assertEqual(metrics.recorded()["bundle_size"], 100)

    def test_the_badge_shows_the_frontend_size_once_measured(self):
        rows = badgekit.integration_rows({"version": "1"}, {}, "o/r", measured_values={"bundle_size": 2048})
        text = " ".join(str(badge) for row in rows for badge in row.badges)
        self.assertIn("frontend%20size", text)


if __name__ == "__main__":
    unittest.main()
