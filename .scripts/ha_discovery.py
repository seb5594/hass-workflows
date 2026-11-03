"""Discover installable stable and upcoming Home Assistant releases from PyPI."""
import json
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version


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


def discover():
    """Latest stable plus latest alpha/dev, beta and RC newer than stable.

    The newest published test plugin is used. Its Core pin is explicitly
    overridden for forward testing; all other dependency requirements still apply.
    Missing packages or metadata fail discovery instead of reporting stale success.
    """
    core = fetch("homeassistant")
    versions = published_versions(core)
    stable = max(version for version in versions if not version.is_prerelease)
    chosen = [stable]
    for channel in ("a", "b", "rc"):
        candidates = [version for version in versions if version > stable and version.is_prerelease
                      and ((version.pre and version.pre[0] == channel)
                           or (channel == "a" and version.is_devrelease))]
        if candidates:
            chosen.append(max(candidates))
    plugin = fetch("pytest-homeassistant-custom-component")["info"]
    return [target(version, plugin) for version in sorted(set(chosen))]


def target(version, plugin):
    info = fetch("homeassistant", str(version))["info"]
    specs = [SpecifierSet(info["requires_python"]), SpecifierSet(plugin["requires_python"] or "")]
    python = next((f"3.{minor}" for minor in range(9, 21)
                   if all(spec.contains(f"3.{minor}.99") for spec in specs)), None)
    if python is None:
        raise ValueError(f"Cannot choose Python for Home Assistant {version}")
    core_pin = next((Requirement(item) for item in plugin["requires_dist"]
                     if Requirement(item).name == "homeassistant"), None)
    if core_pin is None:
        raise ValueError("The test plugin no longer declares Home Assistant")
    return {"homeassistant": str(version), "python": python, "plugin": plugin["version"],
            "preview": version.is_prerelease, "live": True,
            "override_core": not core_pin.specifier.contains(version, prereleases=True)}
