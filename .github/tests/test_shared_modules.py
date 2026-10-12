"""The small shared modules: templating, git operations, badge ordering."""
import subprocess
import unittest
from unittest import mock

from support import ENGINE  # noqa: F401

import badgekit
import config
import github_api
import gitops
import live
import templating


class Templating(unittest.TestCase):
    def test_values_fill_placeholders(self):
        self.assertEqual(templating.fill("a {{ONE}} b", {"ONE": "1"}), "a 1 b")

    def test_missing_unused_and_repeated_placeholders_fail(self):
        with self.assertRaisesRegex(ValueError, "without a value"):
            templating.fill("{{ONE}}", {})
        with self.assertRaisesRegex(ValueError, "does not use"):
            templating.fill("text", {"ONE": "1"})
        with self.assertRaisesRegex(ValueError, "more than once"):
            templating.fill("{{ONE}} {{ONE}}", {"ONE": "1"})
        self.assertEqual(templating.fill("{{ONE}} {{ONE}}", {"ONE": "1"}, once=False), "1 1")

    def test_a_placeholder_line_with_an_empty_value_disappears(self):
        self.assertEqual(templating.fill("a\n__LINE__\nb\n", {"LINE": ""}, templating.DUNDER), "a\nb\n")
        self.assertEqual(templating.fill("a\n  __LINE__\nb\n", {"LINE": "x"}, templating.DUNDER), "a\n  x\nb\n")


class GitOperations(unittest.TestCase):
    def test_token_adds_an_authorization_header_and_never_a_url(self):
        plain, authenticated = gitops.git_command(), gitops.git_command("secret")
        self.assertFalse(any("AUTHORIZATION" in part for part in plain))
        header = next(part for part in authenticated if "AUTHORIZATION" in part)
        self.assertNotIn("secret", header)
        self.assertTrue(any(part.startswith("user.name=") for part in plain))

    def test_nothing_staged_means_no_commit_and_no_push(self):
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0)
        with mock.patch.object(gitops.subprocess, "run", fake_run):
            self.assertFalse(gitops.commit_and_push("message", "main"))
        self.assertFalse(any("commit" in command for command in calls))
        self.assertFalse(any("push" in command for command in calls))

    def test_changes_are_committed_and_pushed_to_the_branch(self):
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 1 if "--quiet" in command else 0)
        with mock.patch.object(gitops.subprocess, "run", fake_run):
            self.assertTrue(gitops.commit_and_push("message", "main", paths=["README.md"]))
        self.assertTrue(any("README.md" in command for command in calls))
        self.assertIn("HEAD:refs/heads/main", calls[-1])

    def test_notification_without_a_token_only_logs(self):
        with mock.patch.object(gitops.github_api, "post_json") as post:
            gitops.notify("update-hub", config.HUB_REPOSITORY, None)
        post.assert_not_called()

    def test_a_failed_notification_is_a_warning_not_an_error(self):
        with mock.patch.object(gitops.github_api, "post_json", side_effect=RuntimeError("HTTP 403")):
            gitops.notify("update-hub", config.HUB_REPOSITORY, "token")

    def test_dispatch_targets_the_repository_events_endpoint(self):
        with mock.patch.object(gitops.github_api, "post_json") as post:
            gitops.dispatch(config.HUB_REPOSITORY, "update-hub", "token", {"a": 1})
        url, payload, token = post.call_args.args
        self.assertTrue(url.endswith(f"/repos/{config.HUB_REPOSITORY}/dispatches"))
        self.assertEqual((payload["event_type"], token), ("update-hub", "token"))


class LiveFacts(unittest.TestCase):
    """Facts travel through the real HTTP layer; only the network itself is replaced."""

    ANSWERS = {
        "/pulls": '[{"number": 9}]',
        "/releases": '[{"draft": false, "assets": [{"download_count": 4}]}, {"draft": true, "assets": []}]',
        "/actions/workflows/": '{"total_count": 7}',
    }

    def answer(self, url, accept, token=None, data=None):
        found = next((text for part, text in self.ANSWERS.items() if part in url), None)
        return found or ('{"stargazers_count": 2, "forks_count": 1, "open_issues_count": 4, '
                         '"license": {"spdx_id": "MIT"}}')

    def test_facts_are_assembled_from_the_api_answers(self):
        with mock.patch.object(github_api, "_request", side_effect=self.answer) as request:
            facts = live.fetch("seb5594/demo", token="secret")
        self.assertEqual(facts, {"license": "MIT", "stars": 2, "forks": 1, "issues": 3, "releases": 1,
                                 "downloads": 4, "latest_downloads": 4, "builds": 7})
        self.assertTrue(all(call.args[2] == "secret" for call in request.call_args_list))

    def test_a_missing_workflow_means_nothing_there(self):
        def missing(url, accept, token=None, data=None):
            if "/actions/" in url:
                raise RuntimeError(f"GitHub returned HTTP 404: {url}")
            return self.answer(url, accept)
        with mock.patch.object(github_api, "_request", side_effect=missing):
            facts = live.fetch("seb5594/demo")
        self.assertEqual(facts["builds"], 0)


class BadgeOrdering(unittest.TestCase):
    def test_architectures_follow_the_canonical_order(self):
        data = {"arch": ["i386", "armhf", "amd64", "aarch64"], "version": "1", "map": []}
        row = badgekit.render([badgekit.app_rows(data, "o/n", None)[badgekit.APP_LAYOUT.index(["arch"])]])
        self.assertIn("amd64%20%C2%B7%20aarch64%20%C2%B7%20armhf%20%C2%B7%20i386", row)

    def test_mounts_are_one_sorted_badge_and_mark_writable_folders(self):
        readonly = badgekit.mount_badges({"map": ["share:ro", "config:ro", "all_addon_configs:ro"]})
        self.assertEqual(len(readonly), 1)
        self.assertIn("mounts%20%28read-only%29", readonly[0])
        self.assertIn("app%20configs%20%C2%B7%20config%20%C2%B7%20share", readonly[0])
        mixed = badgekit.mount_badges({"map": [{"type": "config", "read_only": False}, "share:ro"]})
        self.assertIn("config%20%28rw%29%20%C2%B7%20share", mixed[0])
        self.assertEqual(len(badgekit.mount_badges({"map": ["config:ro"], "devices": ["/dev/sda1"]})), 2)


if __name__ == "__main__":
    unittest.main()
