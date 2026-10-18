"""Facts about a repository that decide which README badges have something to show."""
import github_api

API = "https://api.github.com"


def _json(url, token=None):
    return github_api.fetch_json(url, token)


def _optional(url, default, token=None):
    """A 404 (the workflow does not exist yet) means 'nothing there', not an error."""
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
    # GitHub counts open pull requests as issues; subtracting them avoids the search API and its
    # much stricter rate limit.
    open_pulls = len(_json(f"{API}/repos/{repository}/pulls?state=open&per_page=100", token))
    open_issues = max(info.get("open_issues_count", 0) - open_pulls, 0)
    releases = [r for r in _json(f"{API}/repos/{repository}/releases?per_page=100", token)
                if not r.get("draft")]
    runs = _optional(f"{API}/repos/{repository}/actions/workflows/{workflow}/runs?per_page=1", {}, token)
    return {
        "license": (info.get("license") or {}).get("spdx_id") or "",
        "stars": info.get("stargazers_count", 0),
        "forks": info.get("forks_count", 0),
        "issues": open_issues,
        "releases": len(releases),
        "latest_tag": releases[0]["tag_name"] if releases else "",
        "downloads": sum(downloads(release) for release in releases),
        "builds": runs.get("total_count", 0),
    }


def fetch_own(repository, workflow, token=None):
    """Facts for the repository running this workflow, shown in its header; None when unavailable."""
    try:
        return fetch(repository, workflow, token)
    except RuntimeError as error:
        print(f"::warning::Header badges keep their defaults: {error}")
        return None
