"""Pipeline measurements that end up as plain README badges.

Build, test and packaging steps call `record()` while they run. The README refresh then folds
those raw values into `.github/metrics.json` of the project, which is committed together with the
README. Badges are rendered from that file as ordinary static Shields badges, so a README never
depends on an extra branch or on an endpoint that can disappear.

A value that was not measured in the current run (an unreadable package page, a run without
tests) keeps its previous value instead of vanishing from the README.
"""
import json
import os
import re
import tempfile
import urllib.request
from pathlib import Path

from common import image_repository

RUN_STORE = Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())) / "hass-metrics.json"
SNAPSHOT = Path(".github/metrics.json")
PACKAGE_PAGE = "https://github.com/users/{owner}/packages/container/package/{package}"
DOWNLOADS = re.compile(r'Total downloads</span>\s*<h3 title="(\d+)"')

# Raw keys written by record() that make it into the snapshot. Image sizes are recorded per
# architecture as "image_size.<arch>" and stored together as one mapping.
IMAGE_SIZE_PREFIX = "image_size."
DISPLAYED = ("tests", "runtime_tests", "zip_size", "image_pulls")


def recorded():
    """Raw values recorded by the steps of the current run."""
    return json.loads(RUN_STORE.read_text()) if RUN_STORE.exists() else {}


def record(key, value):
    values = recorded()
    values[key] = value
    RUN_STORE.write_text(json.dumps(values, indent=2))


def load(root=Path(".")):
    """The committed snapshot of a project; empty when it has none yet."""
    path = root / SNAPSHOT
    return json.loads(path.read_text()) if path.exists() else {}


def mebibytes(num_bytes):
    return f"{num_bytes / 1024 / 1024:.1f} MiB"


def human_size(num_bytes):
    """Small files such as an integration ZIP in KiB, everything from 1 MiB on in MiB."""
    return f"{num_bytes / 1024:.1f} KiB" if num_bytes < 1024 * 1024 else mebibytes(num_bytes)


def compact_count(number):
    """1234 -> 1.2k, so a growing counter only changes the README every few hundred pulls."""
    for limit, suffix in ((1_000_000, "M"), (1_000, "k")):
        if number >= limit:
            return f"{number / limit:.1f}".rstrip("0").rstrip(".") + suffix
    return str(number)


def package_pulls(owner, package):
    """Total pulls shown on a public GHCR package page; None when it cannot be read."""
    url = PACKAGE_PAGE.format(owner=owner, package=package)
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            match = DOWNLOADS.search(response.read().decode())
    except OSError:
        return None
    return int(match.group(1)) if match else None


def display(key, value):
    """The text a badge shows for a stored value."""
    if key == "image_size":
        return {arch: mebibytes(size) for arch, size in value.items()}
    return {"zip_size": human_size, "image_pulls": compact_count}.get(key, str)(value)


def merge(previous, values):
    """New measurements replace old ones; anything not measured this time is kept.

    Byte counts and pull counters change on almost every run. A new value is only taken over when
    the badge would show something different, so the README is not committed for nothing.
    """
    measured = {key: values[key] for key in DISPLAYED if values.get(key) is not None}
    sizes = {key.removeprefix(IMAGE_SIZE_PREFIX): value for key, value in values.items()
             if key.startswith(IMAGE_SIZE_PREFIX)}
    if sizes:
        measured["image_size"] = sizes
    snapshot = dict(previous)
    for key, value in measured.items():
        if key not in previous or display(key, value) != display(key, previous[key]):
            snapshot[key] = value
    return snapshot


def update_snapshot(root=Path("."), slug=None, owner=None):
    """Fold this run's values into .github/metrics.json; returns True when the file changed."""
    values = recorded()
    if slug and owner:
        values["image_pulls"] = package_pulls(owner, image_repository(owner,slug).rsplit("/",1)[1])
    path = root / SNAPSHOT
    previous = load(root)
    snapshot = merge(previous, values)
    if snapshot == previous:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    return True
