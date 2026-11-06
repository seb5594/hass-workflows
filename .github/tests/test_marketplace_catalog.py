import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".scripts"))
import marketplace_catalog as catalog


class CatalogSubmissionTests(unittest.TestCase):
    def test_listing_preserves_and_sorts_existing_repositories(self):
        content = base64.b64encode(json.dumps(["z/existing", "A/existing"]).encode())
        self.assertEqual(json.loads(catalog.proposed_catalog(content, "b/new")),
                         ["A/existing", "b/new", "z/existing"])
        self.assertIsNone(catalog.proposed_catalog(content, "A/existing"))

    def test_submission_reuses_open_pr_once_the_release_commit_was_validated(self):
        calls = []
        successful_runs = []
        def api(path, payload=None, **kwargs):
            calls.append((path, payload))
            if path == "repos/hacs/default":
                return {"default_branch": "master"}
            if path.endswith("/git/ref/heads/master"):
                return {"object": {"sha": "upstream"}}
            if "/contents/integration?" in path:
                return {"content": base64.b64encode(b"[]").decode()}
            if path.endswith("/releases/latest"):
                return {"tag_name": "v1.0.0", "html_url": "https://example/release"}
            if path == "user":
                return {"login": "owner"}
            if "/commits/v1.0.0" in path:
                return {"sha": "validated"}
            if "/actions/workflows/" in path:
                return {"total_count": len(successful_runs)}
            if "/pulls?state=open" in path:
                return [{"html_url": "https://example/existing-pr"}]
            raise AssertionError(path)
        env = {"GITHUB_REPOSITORY": "owner/integration", "GITHUB_SHA": "later-commit",
               "GITHUB_RUN_ID": "123", "GH_TOKEN": "test"}
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as folder:
            try:
                os.chdir(folder)
                with patch.dict(os.environ, env), patch.object(sys, "argv", ["script", "--submit"]), patch.object(catalog, "api", side_effect=api):
                    with self.assertRaisesRegex(ValueError, "on the commit of the latest release"):
                        catalog.main()
                    successful_runs.append({"event": "workflow_dispatch"})
                    catalog.main()
                self.assertTrue(all(payload is None for _, payload in calls))
            finally:
                os.chdir(previous)

    def test_validation_run_works_before_the_first_release(self):
        def api(path, payload=None, **kwargs):
            if path == "repos/hacs/default":
                return {"default_branch": "master"}
            if path.endswith("/git/ref/heads/master"):
                return {"object": {"sha": "upstream"}}
            if "/contents/integration?" in path:
                return {"content": base64.b64encode(b"[]").decode()}
            raise subprocess.CalledProcessError(1, "gh")  # releases/latest: no release yet
        env = {"GITHUB_REPOSITORY": "owner/integration", "GITHUB_SHA": "sha", "GITHUB_RUN_ID": "1"}
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as folder:
            try:
                os.chdir(folder)
                with patch.dict(os.environ, env), patch.object(sys, "argv", ["script"]), patch.object(catalog, "api", side_effect=api):
                    catalog.main()
                self.assertIn("none yet", Path(".marketplace-submission/instructions.md").read_text())
            finally:
                os.chdir(previous)
