"""Discover installable stable and upcoming Home Assistant releases from PyPI."""
import datetime
import json
import os
import re
import subprocess
import time
from functools import lru_cache
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

CORE_REPO = "https://github.com/home-assistant/core.git"
FIRST_OFFICIAL_STABLE = Version("2026.11.0")


def fixture_commit(version):
    """Resolve the release tag, peeling annotated tags to their immutable commit."""
    ref = f"refs/tags/{version}"
    lines = subprocess.check_output(
        ["git", "ls-remote", "--exit-code", CORE_REPO, ref, ref + "^{}"], text=True, timeout=60
    )
    refs = {name: sha for sha, name in (line.split() for line in lines.splitlines())}
    commit = refs.get(ref + "^{}") or refs.get(ref, "")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError(f"No Core commit for {version}")
    return commit


@lru_cache(maxsize=None)
def fetch(package, version=None):
    suffix = f"/{version}" if version else ""
    url = f"https://pypi.org/pypi/{package}{suffix}/json"
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={"User-Agent": "hass-workflows-compatibility"}), timeout=30) as response:
                return json.load(response)
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def published_versions(payload):
    result = []
    for text, files in payload["releases"].items():
        try:
            version = Version(text)
        except InvalidVersion:
            continue
        if files and any(not file.get("yanked", False) for file in files):
            result.append(version)
    return result


def preview_summary(chosen, today):
    """Show availability for the full next calendar month, including across New Year."""
    month = today.replace(day=28) + datetime.timedelta(days=4)
    series = (month.year, month.month)
    lines = [f"### Core preview outlook for {month.year}.{month.month}"]
    for channel, name in (("b", "Beta"), ("rc", "Release candidate")):
        versions = [v for v in chosen if v.release[:2] == series and v.pre and v.pre[0] == channel]
        lines.append(f"- {name}: " + (str(max(versions)) if versions else "no published upcoming target"))
    return "\n".join(lines)


def discover():
    """Latest stable plus latest alpha/dev, beta and RC newer than stable.

    The newest published test plugin is used. Its Core pin is explicitly
    overridden for forward testing; all other dependency requirements still apply.
    Missing packages or metadata fail discovery instead of reporting stale success.
    """
    core = fetch("homeassistant")
    versions = published_versions(core)
    stable = max(version for version in versions if not version.is_prerelease)
    previews = {}
    for version in sorted(versions):
        if version > stable and version.is_prerelease:
            channel = version.pre[0] if version.pre else "a"
            previews[(version.release[:2], channel)] = version
    chosen = [stable, *previews.values()]
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a") as output:
            print(preview_summary(chosen, datetime.datetime.now(datetime.timezone.utc).date()), file=output)
    # Core now publishes its own fixtures at the exact Core version, including betas.
    official = set(published_versions(fetch("pytest-homeassistant")))
    if all(version in official or version >= FIRST_OFFICIAL_STABLE for version in chosen):
        return [official_target(version, version in official) for version in sorted(set(chosen))]
    payload = fetch("pytest-homeassistant-custom-component")
    plugin = payload["info"]
    stable_plugin = plugin
    if not core_requirement(plugin).specifier.contains(stable, prereleases=True):
        # Plugin releases can already track a beta while stable Core still needs
        # its previous fixtures. Find the matching published plugin for stable.
        candidates = sorted(published_versions(payload), reverse=True)
        for candidate in candidates[:30]:
            info = fetch("pytest-homeassistant-custom-component", str(candidate))["info"]
            if core_requirement(info).specifier.contains(stable, prereleases=True):
                stable_plugin = info
                break
    return [official_target(version, version in official) if version in official or version >= FIRST_OFFICIAL_STABLE
            else target(version, stable_plugin if version == stable else plugin)
            for version in sorted(set(chosen))]


def official_target(version, published=True, read=None):
    read = read or fetch
    if not published:
        info = read("homeassistant", str(version))["info"]
        return {"homeassistant": str(version), "python": python_minor(info["requires_python"]),
                "plugin": str(version), "plugin_package": "pytest-homeassistant",
                "fixture_commit": fixture_commit(version), "preview": version.is_prerelease,
                "live": True, "override_core": False}
    info = read("pytest-homeassistant", str(version))["info"]
    result = target(version, info, read)
    if result["override_core"]:
        raise ValueError(f"pytest-homeassistant {version} requires a different Core")
    return {**result, "plugin_package": "pytest-homeassistant"}


def core_requirement(plugin):
    requirement = next((Requirement(item) for item in plugin["requires_dist"]
                        if Requirement(item).name == "homeassistant"), None)
    if requirement is None:
        raise ValueError("The test plugin no longer declares Home Assistant")
    return requirement


def target(version, plugin, read=None):
    info = (read or fetch)("homeassistant", str(version))["info"]
    python = python_minor(info["requires_python"], plugin["requires_python"])
    core_pin = core_requirement(plugin)
    return {"homeassistant": str(version), "python": python, "plugin": plugin["version"],
            "preview": version.is_prerelease, "live": True,
            "override_core": not core_pin.specifier.contains(version, prereleases=True)}


def python_minor(*requirements):
    specs = [SpecifierSet(spec or "") for spec in requirements]
    for minor in range(9, 21):
        if all(spec.contains(f"3.{minor}.99") for spec in specs):
            return f"3.{minor}"
    raise ValueError(f"No supported Python for {requirements}")
