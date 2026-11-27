"""Find the earliest tested stable Core patch between a known failure and a known pass."""
import json
import re
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache

from packaging.requirements import Requirement
from packaging.version import Version

import ha_discovery
from ha_matrix import RELEASES, SUPPORT_YEARS, version_key

PLUGIN = "pytest-homeassistant-custom-component"
# The matching plugin release follows its Core release within weeks.
PLUGIN_WINDOW = timedelta(days=75)


def gap_candidates(failed, passed, published):
    """Every installable stable patch strictly between the two observed endpoints."""
    low, high = version_key(failed), version_key(passed)
    return sorted((v for v in published if low < version_key(v) < high), key=version_key)


def stable_versions(core):
    return [text for text, files in core["releases"].items()
            if re.fullmatch(r"\d+\.\d+\.\d+", text) and files and any(not f.get("yanked") for f in files)]


def upload_time(files):
    return datetime.fromisoformat(min(item["upload_time"] for item in files))


def matching_plugin(version, core, plugin_releases, fetch=ha_discovery.fetch):
    """The nearest published test plugin that pins exactly this Core version."""
    released = upload_time(core["releases"][version])
    window = []
    for text, files in plugin_releases["releases"].items():
        available = [f for f in files if not f.get("yanked")]
        if available:
            uploaded = upload_time(available)
            if released - timedelta(days=2) <= uploaded <= released + PLUGIN_WINDOW:
                window.append((abs(uploaded - released), Version(text), text))
    for _, _, text in sorted(window):
        info = fetch(PLUGIN, text)["info"]
        pins = [Requirement(item) for item in info.get("requires_dist") or []
                if Requirement(item).name == "homeassistant"]
        if pins and str(pins[0].specifier) == f"=={version}":
            return info
    return None


# Pins every release before the given one needs: its aiodns breaks with the current pycares.
OLDER_THAN_PINS = (("2026.1.0", ["pycares<5"]),)


def table_pins(version):
    """Dependency pins of the curated release at or below `version`; later ones broke older Cores."""
    table = sorted(json.loads(RELEASES.read_text()), key=lambda item: version_key(item["homeassistant"]))
    below = [item for item in table if version_key(item["homeassistant"]) <= version_key(version)]
    return list((below[-1] if below else table[0]).get("pins", []))


def build_target(version, core, plugin_releases=None, fetch=ha_discovery.fetch):
    """A matrix target for one exact release, or None when no test plugin matches it."""
    parsed = Version(version)
    if parsed >= ha_discovery.FIRST_OFFICIAL_STABLE:
        official = fetch("pytest-homeassistant")["releases"].get(version, [])
        return ha_discovery.official_target(parsed, any(not f.get("yanked") for f in official), fetch)
    plugin = matching_plugin(version, core, plugin_releases if plugin_releases is not None else fetch(PLUGIN), fetch)
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
    if version not in stable_versions(core):
        return None
    target = build_target(version, core, fetch=fetch)
    return target and {**target, "note": "declared minimum"}


def window_anchor(today=None, fetch=ha_discovery.fetch):
    """Select a testable release that was already public five calendar years ago."""
    today = today or datetime.now(timezone.utc).date()
    year = today.year - SUPPORT_YEARS
    cutoff = date(year, 2, 28) if (today.month, today.day) == (2, 29) else today.replace(year=year)
    core = fetch("homeassistant")
    curated = {item["homeassistant"]: item for item in json.loads(RELEASES.read_text())}
    for version in sorted(stable_versions(core), key=version_key, reverse=True):
        files = [f for f in core["releases"][version] if not f.get("yanked")]
        if upload_time(files).date() <= cutoff:
            target = curated.get(version) or build_target(version, core, fetch=fetch)
            if target:
                return target
    raise ValueError(f"No testable Home Assistant Core release at or before {cutoff}")


def history_anchors(targets, minimum, fetch=ha_discovery.fetch):
    """Cover half-years that have no curated or declared stable checkpoint."""
    def half(version):
        year, month = version_key(version)[:2]
        return year, (month - 1) // 6

    covered = {half(item["homeassistant"]) for item in targets if not item.get("preview")}
    core = fetch("homeassistant")
    extra = []
    for version in sorted(stable_versions(core), key=version_key, reverse=True):
        period = half(version)
        if period in covered or version_key(version) < version_key(minimum):
            continue
        target = build_target(version, core, fetch=fetch)
        if target:
            extra.append({**target, "note": "historical checkpoint"})
            covered.add(period)
    return extra


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
    """Bisect published patches lazily. Return only an observed passing patch."""
    read = lru_cache(maxsize=None)(fetch)
    core = read("homeassistant")
    candidates = gap_candidates(failed, passed, stable_versions(core))
    if not candidates:
        return passed

    def probe(version):
        target = build_target(version, core, fetch=read)
        return passes(target) if target else None

    return bisect(candidates, probe) or passed
