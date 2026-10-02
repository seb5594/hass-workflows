"""Collect pipeline metrics and publish them as Shields endpoint badges.

Steps record raw values with `record()`. `render` turns them into one JSON file per
badge and `publish` force-pushes those files to the `badges` branch of the project,
where the generated README badges read them.
"""
import base64
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import badgekit
from common import run

STORE = Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())) / "hass-metrics.json"
OUTPUT = STORE.with_name("hass-badges")
PACKAGE_PAGE = "https://github.com/users/{owner}/packages/container/package/{package}"
DOWNLOADS = re.compile(r'Total downloads</span>\s*<h3 title="(\d+)"')


def load():
    return json.loads(STORE.read_text()) if STORE.exists() else {}


def record(key, value):
    metrics = load()
    metrics[key] = value
    STORE.write_text(json.dumps(metrics, indent=2))


def size(num_bytes):
    return f"{num_bytes / 1024 / 1024:.1f} MiB"


def duration(seconds):
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes}m {seconds:02d}s" if minutes else f"{seconds}s"


def package_pulls(owner, package):
    """Total pulls shown on a public GHCR package page; None when it cannot be read."""
    url = PACKAGE_PAGE.format(owner=owner, package=package)
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            match = DOWNLOADS.search(response.read().decode())
    except OSError:
        return None
    return int(match.group(1)) if match else None


def badges(metrics, slug=None, owner=None):
    """Map badge file names to (label, message, color)."""
    result = {"last-build": ("last build", datetime.now(timezone.utc).strftime("%Y-%m-%d"), "info")}
    for key, value in metrics.items():
        if key.startswith("image_size."):
            arch = key.split(".", 1)[1]
            result[f"image-size-{arch}"] = (f"{arch} image", size(value), "ok")
    if "runtime_tests" in metrics:
        result["runtime-tests"] = ("runtime tests", f"{metrics['runtime_tests']} passed", "stable")
    if "tests" in metrics:
        result["tests"] = ("tests", f"{metrics['tests']} passed", "stable")
    if "zip_size" in metrics:
        result["zip-size"] = ("HACS zip", size(metrics["zip_size"]), "ok")
    if slug and (pulls := package_pulls(owner, f"hass-{slug}")) is not None:
        result["image-pulls"] = ("image pulls", f"{pulls:,}", "info")
    return result


def render(slug=None, owner=None):
    shutil.rmtree(OUTPUT, ignore_errors=True)
    OUTPUT.mkdir(parents=True)
    for name, (label, message, color) in badges(load(), slug, owner).items():
        (OUTPUT / f"{name}.json").write_text(badgekit.dump_endpoint(label, message, color))
    return sorted(path.name for path in OUTPUT.iterdir())


def publish(repository, token):
    """Replace the badges branch with a single fresh commit; history is not needed."""
    credentials = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    git = ["git", "-c", f"http.https://github.com/.extraheader=AUTHORIZATION: basic {credentials}",
           "-c", "user.name=github-actions[bot]",
           "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com"]
    with tempfile.TemporaryDirectory() as work:
        run(*git[:1], "init", "-q", "-b", "badges", work)
        for path in OUTPUT.iterdir():
            shutil.copy(path, work)
        run(*git, "-C", work, "add", "--all")
        run(*git, "-C", work, "commit", "-q", "-m", "chore: update pipeline metrics")
        run(*git, "-C", work, "push", "-q", "--force",
            f"https://github.com/{repository}.git", "badges")


def main(command, kind, slug):
    owner, repository = None, os.environ.get("GITHUB_REPOSITORY", "")
    if repository:
        owner = repository.split("/")[0]
    files = render(slug if kind == "app" else None, owner)
    print("Rendered badges:", ", ".join(files))
    if command == "publish":
        publish(repository, os.environ["GH_TOKEN"])


if __name__ == "__main__":
    main(*sys.argv[1:4])
