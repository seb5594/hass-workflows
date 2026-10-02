"""Small GitHub helpers shared by the catalog, hub and live-fact scripts."""
import json
import os
import time
import urllib.error
import urllib.request

import config

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _request(url, accept, token=None, data=None):
    headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28", "User-Agent": config.USER_AGENT}
    if token := token or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        headers["Content-Type"] = "application/json"
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers=headers, data=data)
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            if error.code not in RETRYABLE_STATUS or attempt == 3:
                raise RuntimeError(f"GitHub returned HTTP {error.code}: {url}") from error
        except (urllib.error.URLError, TimeoutError):
            if attempt == 3:
                raise
        time.sleep(2 ** attempt)


def fetch_json(url, token=None):
    return json.loads(_request(url, "application/vnd.github+json", token))


def fetch_text(url, token=None):
    return _request(url, "text/plain", token)


def post_json(url, payload, token=None):
    """POST a JSON body, e.g. a repository_dispatch event."""
    return _request(url, "application/vnd.github+json", token, json.dumps(payload).encode())
