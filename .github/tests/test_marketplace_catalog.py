import base64
import json
import os
from pathlib import Path
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

    def test_submission_reuses_open_pr_and_requires_validation_before_release(self):
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
                return {"tag_name": "v1.0.0", "html_url": "https://example/release",
                        "published_at": "2026-11-06T12:00:00Z"}
            if path == "user":
                return {"login": "owner"}
            if "/commits/v1.0.0" in path:
                return {"sha": "validated"}
            if "/actions/workflows/" in path:
                return {"workflow_runs": successful_runs}
            if "/pulls?state=open" in path:
                return [{"html_url": "https://example/existing-pr"}]
            raise AssertionError(path)
        env = {"GITHUB_REPOSITORY": "owner/integration", "GITHUB_SHA": "validated",
               "GITHUB_RUN_ID": "123", "GH_TOKEN": "test"}
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as folder:
            try:
                os.chdir(folder)
                with patch.dict(os.environ, env), patch.object(sys, "argv", ["script", "--submit"]), patch.object(catalog, "api", side_effect=api):
                    with self.assertRaisesRegex(ValueError, "Publish a release"):
                        catalog.main()
                    successful_runs.append({"updated_at": "2026-11-06T11:00:00Z",
                                            "event": "workflow_dispatch"})
                    catalog.main()
                self.assertTrue(all(payload is None for _, payload in calls))
            finally:
                os.chdir(previous)
