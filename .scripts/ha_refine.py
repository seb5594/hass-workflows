"""Narrow the minimum Home Assistant version down between a failed and a passed release.

The compatibility matrix only knows the curated releases of ha_releases.json. When one of them
fails and the next one passes, the true boundary lies somewhere in between. This module lists the
`.0` release of every series in that gap, builds a test target for each (the plugin that pins that
exact Core, the lowest Python it allows) and bisects over them, so the boundary is found with a
handful of environments instead of one per series.
"""
import json
import re
from datetime import datetime, timedelta

from packaging.requirements import Requirement
from packaging.version import Version

import ha_discovery
from ha_matrix import RELEASES, version_key

PLUGIN = "pytest-homeassistant-custom-component"
# The matching plugin release follows its Core release within weeks.
PLUGIN_WINDOW = timedelta(days=75)


def series(version):
    return version_key(version)[:2]


def gap_candidates(failed, passed, published):
    """`Y.M.0` of every stable series above `failed` up to and including that of `passed`."""
    wanted = {f"{major}.{minor}.0" for major, minor, *_ in map(version_key, published)
              if series(failed) < (major, minor) <= series(passed)}
    return sorted(wanted, key=version_key)


def stable_versions(core):
    return [text for text, files in core["releases"].items()
            if re.fullmatch(r"\d+\.\d+\.\d+", text) and files and any(not f.get("yanked") for f in files)]


def upload_time(files):
    return datetime.fromisoformat(min(item["upload_time"] for item in files))


def matching_plugin(version, core, plugin_releases, fetch=ha_discovery.fetch):
    """The newest plugin release whose Core requirement is exactly `version`, or None."""
    released = upload_time(core["releases"][version])
    window = sorted((text for text, files in plugin_releases["releases"].items() if files
                     and released - timedelta(days=2) <= upload_time(files) <= released + PLUGIN_WINDOW),
                    key=lambda text: upload_time(plugin_releases["releases"][text]))
    for text in window:
        info = fetch(PLUGIN, text)["info"]
        pins = [Requirement(item) for item in info.get("requires_dist") or []
                if Requirement(item).name == "homeassistant"]
        if pins and str(pins[0].specifier) == f"=={version}":
            return info
    return None


def series_target(label, core, plugin_releases, fetch=ha_discovery.fetch):
    """A target for the series named `Y.M.0`: its first release, else the next one a plugin matches."""
    wanted = series(label)
    patches = sorted((text for text in stable_versions(core) if series(text) == wanted), key=version_key)
    for version in patches:
        target = build_target(version, core, plugin_releases, fetch)
        if target:
            return target
    return None


# Pins every release before the given one needs: its aiodns breaks with the current pycares.
OLDER_THAN_PINS = (("2026.1.0", ["pycares<5"]),)


def table_pins(version):
    """Dependency pins of the curated release at or below `version`; later ones broke older Cores."""
    table = sorted(json.loads(RELEASES.read_text()), key=lambda item: version_key(item["homeassistant"]))
    below = [item for item in table if version_key(item["homeassistant"]) <= version_key(version)]
    return list((below[-1] if below else table[0]).get("pins", []))


def build_target(version, core, plugin_releases, fetch=ha_discovery.fetch):
    """A matrix target for one exact release, or None when no test plugin matches it."""
    plugin = matching_plugin(version, core, plugin_releases, fetch)
    if plugin is None:
        return None
    info = fetch("homeassistant", version)["info"]
    target = {"homeassistant": version, "plugin": plugin["version"], "preview": False,
              "python": ha_discovery.python_minor(info["requires_python"], plugin["requires_python"]),
              "note": "boundary search"}
    pins = table_pins(version) + [pin for before, extra in OLDER_THAN_PINS
                                  if version_key(version) < version_key(before) for pin in extra]
    if pins:
        target["pins"] = pins
    return target


def exact_target(version, fetch=ha_discovery.fetch):
    """A target for exactly `version` (for example a project's declared minimum), or None."""
    core = fetch("homeassistant")
    if version not in core["releases"]:
        return None
    target = build_target(version, core, fetch(PLUGIN), fetch)
    return target and {**target, "note": "declared minimum"}


def bisect(candidates, passes):
    """First candidate that passes, assuming everything above it passes too; None if none does.

    `passes` may return None for a candidate that cannot be tested at all (its environment does not
    install); that candidate is dropped instead of counting as a failure.
    """
    candidates = list(candidates)
    low, high = 0, len(candidates)
    while low < high:
        middle = (low + high) // 2
        outcome = passes(candidates[middle])
        if outcome is None:
            del candidates[middle]
            high -= 1
        elif outcome:
            high = middle
        else:
            low = middle + 1
    return candidates[low] if low < len(candidates) else None


def refine(failed, passed, passes, fetch=ha_discovery.fetch):
    """The lowest series (`Y.M.0`) between `failed` and `passed` that passes, or `passed` itself.

    `passes(target)` runs one target. A series is tested at its first release, or at the next one
    a test plugin exists for; a series with no matching plugin at all is skipped.
    """
    core, plugins = fetch("homeassistant"), fetch(PLUGIN)
    targets = {}
    for version in gap_candidates(failed, passed, stable_versions(core)):
        target = series_target(version, core, plugins, fetch)
        if target:
            targets[version] = target
    found = bisect(list(targets), lambda version: passes(targets[version]))
    return found or passed
