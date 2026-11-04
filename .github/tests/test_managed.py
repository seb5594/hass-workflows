"""Protect the files every repository keeps in step with the engine, and the snippets behind them."""
import json
import tempfile
import unittest
from pathlib import Path

import support  # noqa: F401

import config
import managed
import plan
import projectmeta
import templating
from test_templates import make_app, make_integration

SHA = "a" * 40


def make_repository(root, kind):
    """The smallest checkout of each kind that the managed files can be rendered for."""
    if kind == "app":
        app = make_app(root)
        (app / "entrypoint.sh").write_text("#!/bin/bash\n")
    elif kind == "integration":
        make_integration(root)


class SnippetIncludes(unittest.TestCase):
    def snippets(self, **files):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        for name, text in files.items():
            (Path(directory.name) / f"{name}.yml").write_text(text)
        return directory.name

    def test_snippet_takes_the_indentation_of_its_include_line(self):
        snippets = self.snippets(step="- run: one\n  with:\n    key: value\n")
        text = templating.expand_includes("steps:\n    # include: step\nafter: true\n", snippets)
        self.assertEqual(text, "steps:\n    - run: one\n      with:\n        key: value\nafter: true\n")

    def test_unknown_snippets_fail_loudly(self):
        with self.assertRaisesRegex(ValueError, "unknown snippet 'missing'"):
            templating.expand_includes("  # include: missing\n", self.snippets())

    def test_snippets_may_contain_placeholders(self):
        snippets = self.snippets(pin="ref: __SHA__\n")
        text = templating.expand_includes("# include: pin\n", snippets)
        self.assertEqual(templating.fill(text, {"SHA": "abc"}, templating.DUNDER), "ref: abc\n")


class WorkflowTemplates(unittest.TestCase):
    def test_every_workflow_pins_the_engine_and_passes_secrets(self):
        for kind, workflow in {**managed.WORKFLOWS, "compat": managed.COMPATIBILITY}.items():
            text = managed.render_workflow(workflow, SHA)
            self.assertEqual(text.count(f"ref: {SHA}"), text.count("path: .engine"), kind)
            self.assertGreaterEqual(text.count(f"ref: {SHA}"), 1, kind)
            self.assertIn("secrets.ORCHESTRATION_PAT", text, kind)
            self.assertNotIn("# include", text, kind)
            self.assertNotIn("__", text.replace("__pycache__", ""), kind)

    def test_project_callers_differ_only_where_the_kinds_differ(self):
        app, integration = (managed.render_workflow(managed.WORKFLOWS[kind], SHA) for kind in ("app", "integration"))
        self.assertIn("packages: write", app)
        self.assertNotIn("packages: write", integration)
        self.assertIn("timeout-minutes: 90", app)
        self.assertIn("timeout-minutes: 30", integration)
        self.assertIn("name: Home Assistant CI", integration)

    def test_secrets_are_withheld_from_fork_pull_requests(self):
        for workflow in (managed.WORKFLOWS["app"], managed.COMPATIBILITY):
            text = managed.render_workflow(workflow, SHA)
            self.assertIn("github.event.pull_request.head.repo.full_name == github.repository", text)

    def test_compat_caller_tests_every_release_of_the_matrix_in_its_own_job(self):
        text = managed.render_workflow(managed.COMPATIBILITY, SHA)
        self.assertEqual(text.count(f"ref: {SHA}"), 2)
        self.assertIn("./.engine/.actions/ha-targets", text)
        self.assertIn("fromJSON(needs.releases.outputs.releases)", text)
        self.assertIn('ha_matrix.py run --target-json "$HA_TARGET"', (config.ENGINE_ROOT / ".actions/ha-test/action.yml").read_text())
        self.assertIn('ha_matrix.py list --live --matrix', (config.ENGINE_ROOT / ".actions/ha-targets/action.yml").read_text())
        self.assertIn("include: ${{ fromJSON(needs.releases.outputs.releases) }}", text)
        self.assertIn("cron: '41 5 * * *'", text)

    def test_catalog_callers_name_their_own_event_and_kind(self):
        apps, integrations = (managed.render_workflow(managed.WORKFLOWS[kind], SHA)
                              for kind in ("catalog-apps", "catalog-integrations"))
        self.assertIn("types: [update-addons]", apps)
        self.assertIn("./.engine/.actions/catalog-sync", integrations)
        self.assertIn("group: synchronize-integration-catalog", integrations)


class ManagedFiles(unittest.TestCase):
    def repository(self, kind):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        make_repository(root, kind)
        return root

    def test_every_kind_gets_the_shared_files(self):
        for kind in ("app", "integration"):
            root = self.repository(kind)
            files = managed.expected(kind, SHA, root)
            for path in (".github/dependabot.yml", ".github/renovate.json", ".github/FUNDING.yml"):
                self.assertIn(path, files, kind)

    def test_renovate_config_is_the_complete_preset_not_a_reference_to_it(self):
        text = managed.expected("integration", SHA, self.repository("integration"))[".github/renovate.json"]
        found = json.loads(text)
        self.assertEqual(found, json.loads((config.ENGINE_ROOT / "default.json").read_text()))
        self.assertNotIn("github>", text)
        self.assertEqual(found["branchPrefix"], "feature-")
        # Only the default branch is a base: a base branch configured elsewhere, which a repository
        # does not have, produced "Base branch does not exist" and branch names like feature-main-x.
        self.assertEqual(found["baseBranchPatterns"], ["$default"])

    def test_updates_that_are_decisions_rather_than_bumps_are_switched_off(self):
        rules = json.loads(managed.renovate_config())["packageRules"]
        disabled = {(tuple(rule.get("matchManagers", [])), tuple(rule.get("matchDepNames", [])))
                    for rule in rules if rule.get("enabled") is False}
        self.assertIn((("github-actions",), ("python",)), disabled)
        self.assertIn((("github-actions",), ("ubuntu",)), disabled)
        self.assertIn((("homeassistant-manifest",), ()), disabled)

    def test_the_engine_keeps_the_same_renovate_config_itself(self):
        own = (config.ENGINE_ROOT / ".github/renovate.json").read_text()
        self.assertEqual(own, managed.renovate_config())

    def test_funding_comes_from_the_donation_links(self):
        text = managed.expected("integration", SHA, self.repository("integration"))[".github/FUNDING.yml"]
        self.assertIn(f"buy_me_a_coffee: {config.COFFEE_USER}", text)
        self.assertIn(config.PAYPAL_URL, text)

    def test_apps_keep_the_shared_entrypoint_next_to_their_config(self):
        files = managed.expected("app", SHA, self.repository("app"))
        self.assertEqual(files["sample/entrypoint.sh"], (config.ENGINE_ROOT / ".templates/entrypoint.sh").read_text())

    def test_apps_on_s6_have_no_entrypoint_to_manage(self):
        root = self.repository("app")
        (root / "sample/entrypoint.sh").unlink()
        self.assertNotIn("sample/entrypoint.sh", managed.expected("app", SHA, root))

    def test_real_home_assistant_tests_require_the_compatibility_workflow(self):
        root = self.repository("integration")
        managed.sync("integration", SHA, root)
        managed.check("integration", root)
        (root / ".github/ha_tests").mkdir()
        with self.assertRaisesRegex(ValueError, "compat.yml"):
            managed.check("integration", root)
        self.assertEqual(managed.sync("integration", SHA, root), [".github/workflows/compat.yml"])
        managed.check("integration", root)

    def test_catalogs_describe_how_they_are_maintained(self):
        notes = managed.expected("catalog-apps", SHA)[".github/DEVELOPMENT.md"]
        self.assertIn("Git submodule", notes)
        self.assertIn("update-addons", notes)
        files = managed.expected("catalog-integrations", SHA)
        # The integration catalog owns its release-selection guide.
        self.assertNotIn(".github/DEVELOPMENT.md", files)
        self.assertIn("types: [update-integrations]", files[".github/workflows/update.yml"])
        for filename in ("ci", "compat", "release"):
            self.assertIn(f".github/workflows/{filename}.yml", files)

    def test_sync_writes_pins_and_detects_drift(self):
        root = self.repository("app")
        self.assertIn(".github/workflows/ci.yml", managed.sync("app", SHA, root))
        self.assertEqual(managed.sync("app", SHA, root), [])
        managed.check("app", root)
        self.assertEqual(managed.pinned_sha("app", root), SHA)
        self.assertIn(".github/workflows/ci.yml", managed.sync("app", "b" * 40, root))
        self.assertEqual(managed.pinned_sha("app", root), "b" * 40)
        (root / ".github/dependabot.yml").write_text("version: 2\n")
        (root / "sample/entrypoint.sh").write_text("#!/bin/bash\necho local edit\n")
        with self.assertRaises(ValueError) as error:
            managed.check("app", root)
        self.assertIn(".github/dependabot.yml", str(error.exception))
        self.assertIn("sample/entrypoint.sh", str(error.exception))

    def test_a_workflow_without_engine_pin_is_rejected(self):
        root = self.repository("integration")
        managed.sync("integration", SHA, root)
        (root / ".github/workflows/ci.yml").write_text("name: local\n")
        with self.assertRaisesRegex(ValueError, "pin the engine"):
            managed.check("integration", root)


class UpstreamCredentials(unittest.TestCase):
    def test_repository_writes_use_workflow_token_and_dispatch_ci(self):
        import yaml
        workflow = yaml.safe_load(managed.render_workflow(managed.UPSTREAM, SHA))
        self.assertEqual(workflow['permissions']['contents'], 'write')
        self.assertEqual(workflow['permissions']['actions'], 'write')
        for name in ('follow', 'renovate'):
            steps = workflow['jobs'][name]['steps']
            checkouts = [step['with'] for step in steps if step.get('uses', '').startswith('actions/checkout@')]
            self.assertEqual(checkouts[0]['token'], '${{ github.token }}')
            self.assertEqual(checkouts[1]['token'], '${{ secrets.ORCHESTRATION_PAT }}')
            action = steps[-1]["uses"].removeprefix("./.engine/")
            composite = yaml.safe_load((config.ENGINE_ROOT / action / "action.yml").read_text())
            commit = next(step for step in composite["runs"]["steps"] if step.get("name") == "Commit the new version")
            self.assertEqual(commit['env']['GH_TOKEN'], '${{ github.token }}')
            self.assertIn('gh workflow run ci.yml --ref "$TARGET_BRANCH"', commit['run'])
            self.assertIn("git add -u -- '*/config.yaml' '*/Dockerfile' '*/CHANGELOG.md'", commit['run'])


class ProjectListing(unittest.TestCase):
    def test_every_listed_repository_is_unique(self):
        names = [name for names in config.PROJECTS.values() for name in names]
        self.assertEqual(len(names), len(set(names)))

    def test_validation_matrix_covers_every_listed_repository(self):
        include = plan.matrix()["include"]
        self.assertEqual([entry["project"] for entry in include],
                         [name for names in config.PROJECTS.values() for name in names])
        self.assertEqual({entry["kind"] for entry in include}, {"app", "integration"})

    def test_hacs_file_is_optional_for_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_integration(root)
            (root / "hacs.json").unlink()
            self.assertEqual(projectmeta.discover(root).hacs, {})


if __name__ == "__main__":
    unittest.main()
