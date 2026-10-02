"""Facts about a repository that decide which README badges have something to show."""
import urllib.parse

import github_api

API = "https://api.github.com"
USER_AGENT = "seb5594-hass-workflows"


def _json(url, token=None):
    return github_api.fetch_json(url, USER_AGENT, token)


def _optional(url, default, token=None):
    """A 404 (no badges branch, no workflow yet) means 'nothing there', not an error."""
    try:
        return _json(url, token)
    except RuntimeError as error:
        if "HTTP 404" in str(error):
            return default
        raise


def downloads(release):
    return sum(asset["download_count"] for asset in release.get("assets", []))


def fetch(repository, workflow="ci.yml", token=None):
    """Current counts for one repository; raises when GitHub cannot be reached.

    `token` overrides the default one, for repositories the default token cannot read.
    """
    info = _json(f"{API}/repos/{repository}", token)
    open_issues = _json(f"{API}/search/issues?" + urllib.parse.urlencode(
        {"q": f"repo:{repository} type:issue state:open", "per_page": 1}), token)["total_count"]
    releases = [r for r in _json(f"{API}/repos/{repository}/releases?per_page=100", token)
                if not r.get("draft")]
    runs = _optional(f"{API}/repos/{repository}/actions/workflows/{workflow}/runs?per_page=1", {}, token)
    published = _optional(f"{API}/repos/{repository}/contents/?ref=badges", [], token)
    return {
        "license": (info.get("license") or {}).get("spdx_id") or "",
        "stars": info.get("stargazers_count", 0),
        "forks": info.get("forks_count", 0),
        "issues": open_issues,
        "releases": len(releases),
        "downloads": sum(downloads(release) for release in releases),
        "latest_downloads": downloads(releases[0]) if releases else 0,
        "builds": runs.get("total_count", 0),
        # Names of the endpoint files the pipeline published, e.g. {"image-size", "tests"}.
        "metrics": {entry["name"].removesuffix(".json") for entry in published
                    if entry["name"].endswith(".json")},
    }


def fetch_own(repository, workflow, token=None):
    """Facts for the repository running this workflow, shown in its header; None when unavailable."""
    try:
        return fetch(repository, workflow, token)
    except RuntimeError as error:
        print(f"::warning::Header badges keep their defaults: {error}")
        return None
