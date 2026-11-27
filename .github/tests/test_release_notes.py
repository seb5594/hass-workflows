"""Exercise release notes against real Git histories without contacting GitHub."""
import os
import subprocess
import tempfile
import unittest
from contextlib import chdir
from pathlib import Path
from unittest.mock import patch

import support  # noqa: F401
import release_notes as notes


class Classification(unittest.TestCase):
    def test_titles_from_people_and_dependency_bots(self):
        cases = [
            ("feat(card): Add a timer", ("feat", "card · Add a timer")),
            ("fix(api)!: Remove fallback", ("breaking", "api · Remove fallback")),
            ("perf: Poll less often", ("improve", "Poll less often")),
            ("🐛 Keep the card visible", ("fix", "Keep the card visible")),
            ("docs: Explain pairing", ("docs", "Explain pairing")),
            ("ci: Refresh tests", ("chore", "Refresh tests")),
            ("security: Rotate keys", ("security", "Rotate keys")),
            ("Bump actions/checkout from v5 to v6", ("deps", "actions/checkout · v5 → v6")),
            ("chore(deps): Update alpine to 3.24", ("deps", "Update alpine to 3.24")),
            ("📦 Update org/image to 1.3 (was 1.2).", ("deps", "org/image · 1.2 → 1.3")),
            ("Observe the new sensor", ("other", "Observe the new sensor")),
        ]
        for title, expected in cases:
            with self.subTest(title=title):
                self.assertEqual(notes.classify(title), expected)
        self.assertEqual(notes.classify("fix(deps): replace client", body="BREAKING CHANGE: Re-pair")[0], "breaking")

    def test_version_section_keeps_migration_markdown_and_matches_exact_versions(self):
        guide = "### Migration\n\nRe-pair the device.\n\n```yaml\n## sample\n```"
        changelog = f"# Changelog\n## 1.2.0.1\nwrong build\n## [1.2.0] - today\n{guide}\n## 1.1.0\nolder"
        self.assertEqual(notes.version_entry(changelog, "1.2.0"), guide)
        self.assertIn(guide, notes.authored_notes(guide))
        self.assertEqual(notes.version_entry(changelog, "1.2"), "")

    def test_curated_bullets_keep_markdown_and_line_continuations(self):
        body = notes.authored_notes("- 🐛 Keep the **timer**\n  after reload.\n- ✨ Add pairing")
        self.assertEqual(body, "## ✨ New features\n\n- Add pairing\n\n## 🐛 Bug fixes\n\n"
                         "- Keep the **timer**\n  after reload.")


class History(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name) / "source"
        self.folder.mkdir()
        self.enterContext(chdir(self.folder))
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Tester")
        self.git("config", "user.email", "tester@example.org")
        self.commit("Initial installation")
        self.git("tag", "v1.0.0")

    def git(self, *args):
        return subprocess.check_output(["git", *args], text=True).strip()

    def commit(self, title, body=None):
        self.git("commit", "-q", "--allow-empty", "-m", title, *(["-m", body] if body else []))

    def render(self, tag="v1.1.0", changelog=None):
        return notes.generated_notes("owner/demo", tag, self.git("rev-parse", "HEAD"), changelog)

    def test_merge_squash_and_direct_commits_on_the_release_branch(self):
        self.git("switch", "-qc", "feature")
        self.commit("Only the review needs this intermediate commit")
        self.git("tag", "v9.9.9")
        self.git("switch", "-q", "main")
        self.git("merge", "-q", "--no-ff", "feature", "-m", "Merge pull request #42 from owner/feature",
                 "-m", "feat: Add a timer")
        self.commit("Bump the actions group with 2 updates (#43)")
        self.commit("fix: Keep the timer after reload")
        self.commit("docs: refresh README badges")
        self.git("tag", "v1.1.0")
        notes_md = self.render()
        self.assertIn("## ✨ New features\n\n- Add a timer · [#42]", notes_md)
        self.assertIn("[#43](https://github.com/owner/demo/pull/43)", notes_md)
        self.assertIn("## 🐛 Bug fixes\n\n- Keep the timer after reload · [`", notes_md)
        self.assertNotIn("intermediate", notes_md)
        self.assertNotIn("badges", notes_md)
        self.assertNotIn("Initial installation", notes_md)
        self.assertTrue(notes_md.endswith("/compare/v1.0.0...v1.1.0)"))

    def test_bot_identity_and_scoped_branches_classify_group_updates(self):
        with patch.dict(os.environ, {"GIT_AUTHOR_NAME": "dependabot[bot]"}):
            self.commit("Bump the actions group with 2 updates (#10)")
        self.commit("Merge pull request #12 from owner/renovate/pins", "Pin workflow actions")
        self.assertIn("## 📦 Dependency updates\n\n- Pin workflow actions · [#12]", self.render())
        self.assertNotIn("Other changes", self.render())

    def test_app_entry_takes_precedence_and_empty_entries_fall_back_to_history(self):
        path = Path("CHANGELOG.md")
        path.write_text("# Changelog\n## v1.1.0\n* 📦 Update test to 2 (was 1).\n## 1.0.0\nOld")
        self.commit("fix: Restore pairing")
        body = self.render(changelog=path)
        self.assertIn("## 📦 Dependency updates\n\n- test · 1 → 2", body)
        self.assertNotIn("Old", body)
        self.assertNotIn("Restore pairing", body)
        path.write_text("## 1.1.0\n\n## 1.0.0\nOld")
        self.assertIn("Restore pairing", self.render(changelog=path))

    def test_first_release_and_same_commit_tags_have_a_readable_body(self):
        first = self.render("v1.0.0")
        self.assertIn("Initial installation", first)
        self.assertIn("[Commit history]", first)
        self.assertNotIn("/compare/", first)
        self.assertIn("same commit", self.render())

    def test_shallow_caller_reads_the_same_range_without_modifying_its_checkout(self):
        self.commit("fix: Decode the sensor value")
        expected = self.render()
        shallow = self.folder.parent / "caller"
        self.git("config", "uploadpack.allowFilter", "true")
        self.git("clone", "-q", "--depth=1", self.folder.as_uri(), str(shallow))
        with chdir(shallow):
            self.assertEqual(self.render(), expected)
            self.assertEqual(self.git("rev-parse", "--is-shallow-repository"), "true")
            self.assertEqual(self.git("tag", "--list"), "")
