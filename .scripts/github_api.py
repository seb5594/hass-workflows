"""Small GitHub helpers shared by the catalog and hub scripts."""
import json
import os
import time
import urllib.error
import urllib.request

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _request(url, accept, user_agent):
    headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28", "User-Agent": user_agent}
    if token := os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            if error.code not in RETRYABLE_STATUS or attempt == 3:
                raise RuntimeError(f"GitHub returned HTTP {error.code}: {url}") from error
        except (urllib.error.URLError, TimeoutError):
            if attempt == 3:
                raise
        time.sleep(2 ** attempt)


def fetch_json(url, user_agent="seb5594-hass-workflows"):
    return json.loads(_request(url, "application/vnd.github+json", user_agent))


def fetch_text(url, user_agent="seb5594-hass-workflows"):
    return _request(url, "text/plain", user_agent)
