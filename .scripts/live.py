"""Facts about a repository that decide which README badges have something to show."""
import urllib.parse

import github_api

API = "https://api.github.com"
USER_AGENT = "seb5594-hass-workflows"


def _json(url):
    return github_api.fetch_json(url, USER_AGENT)


def _optional(url, default):
    """A 404 (no badges branch, no workflow yet) means 'nothing there', not an error."""
    try:
        return _json(url)
    except RuntimeError as error:
        if "HTTP 404" in str(error):
            return default
        raise


def downloads(release):
    return sum(asset["download_count"] for asset in release.get("assets", []))


def fetch(repository, workflow="ci.yml"):
    """Current counts for one repository; raises when GitHub cannot be reached."""
    info = _json(f"{API}/repos/{repository}")
    open_issues = _json(f"{API}/search/issues?" + urllib.parse.urlencode(
        {"q": f"repo:{repository} type:issue state:open", "per_page": 1}))["total_count"]
    releases = [r for r in _json(f"{API}/repos/{repository}/releases?per_page=100") if not r.get("draft")]
    runs = _optional(f"{API}/repos/{repository}/actions/workflows/{workflow}/runs?per_page=1", {})
    published = _optional(f"{API}/repos/{repository}/contents/?ref=badges", [])
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
