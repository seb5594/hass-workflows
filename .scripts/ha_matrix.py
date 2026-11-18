#!/usr/bin/env python3
"""Run a project's tests against genuine Home Assistant releases.

Each release gets its own virtual environment (made with uv) holding that Home
Assistant and the matching pytest-homeassistant-custom-component. Two suites run
in it, when the project has them:

* .github/tests     the regular suite, with the Home Assistant pytest plugin switched off
* .github/ha_tests  tests against a real Home Assistant core

Historical releases come from ha_releases.json. --live adds the latest stable
and upcoming alpha/dev, beta and RC packages from PyPI, from the oldest release inside the five-year support window (or hacs.json's minimum when that is older).

CLI:
    ha_matrix.py list [--minimum VERSION]    JSON list of releases (for a CI matrix)
    ha_matrix.py list --live --matrix       frozen target objects for matrix.include
    ha_matrix.py run [RELEASE ...]           test the given releases (default: all of them)
    ha_matrix.py run --target-json JSON     run one frozen discovery target
Environment: HASS_MATRIX_DIR keeps the virtual environments between runs.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

RELEASES = Path(__file__).with_name("ha_releases.json")
REGULAR_TESTS = Path(".github/tests")
REAL_TESTS = Path(".github/ha_tests")


def real_tests():
    return REAL_TESTS if REAL_TESTS.is_dir() else Path("tests_ha")

# pip requirements of the integrations a project depends on (bluetooth pulls in usb, ...).
COMPONENT_REQUIREMENTS = """
import importlib.util, json, pathlib, sys
base = pathlib.Path(importlib.util.find_spec("homeassistant").origin).parent / "components"
seen, requirements = set(), []
def collect(domain):
    manifest = base / domain / "manifest.json"
    if domain in seen or not manifest.exists():
        return
    seen.add(domain)
    data = json.loads(manifest.read_text())
    requirements.extend(data.get("requirements", []))
    for dependency in data.get("dependencies", []):
        collect(dependency)
for domain in sys.argv[1:]:
    collect(domain)
print("\\n".join(dict.fromkeys(requirements)))
"""


def version_key(version):
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:(a|b|rc)(\d+))?(?:\.dev(\d+))?", version)
    if not match:
        raise ValueError(f"Unsupported Home Assistant version: {version}")
    major, minor, patch, stage, serial, dev = match.groups()
    return (int(major), int(minor), int(patch),
            {"a": 0, "b": 1, "rc": 2, None: 3}[stage] if dev is None else -1,
            int(serial or dev or 0))


SUPPORT_YEARS = 5


def support_line(today=None):
    """(year, month) of the oldest Home Assistant series that must still work.

    Every release published within the last SUPPORT_YEARS years has to be supported, so the line
    moves forward with the calendar. A series is counted as released from the 8th of its month,
    because the monthly .0 release always lands in the first week; that keeps the line on the
    safe, older side.
    """
    today = today or datetime.date.today()
    day = today.replace(year=today.year - SUPPORT_YEARS, day=28) if (today.month, today.day) == (2, 29) \
        else today.replace(year=today.year - SUPPORT_YEARS)
    return (day.year, day.month) if day.day >= 8 else ((day.year, day.month - 1) if day.month > 1
                                                       else (day.year - 1, 12))


def supported_minimum(declared=None, today=None):
    """Oldest release to test: the curated release at or below the support line.

    A project that declares an even older minimum in hacs.json keeps that one.
    """
    line = support_line(today)
    table = sorted(json.loads(RELEASES.read_text()), key=lambda item: version_key(item["homeassistant"]))
    at_or_below = [item["homeassistant"] for item in table if version_key(item["homeassistant"])[:2] <= line]
    floor = at_or_below[-1] if at_or_below else table[0]["homeassistant"]
    if declared and version_key(declared) < version_key(floor):
        return declared
    return floor


def minimum_from_hacs(root=Path(".")):
    """The `homeassistant` minimum of hacs.json, or None when the project names none."""
    hacs = root / "hacs.json"
    return json.loads(hacs.read_text()).get("homeassistant") if hacs.exists() else None


def releases(minimum=None):
    """Known releases at or above `minimum`, oldest first."""
    table = json.loads(RELEASES.read_text())
    if minimum:
        minimum_key = version_key(minimum)
        table = [item for item in table if version_key(item["homeassistant"]) >= minimum_key]
    else:
        table = [item for item in table if not item.get("opt_in")]
    return sorted(table, key=lambda item: version_key(item["homeassistant"]))


def manifests(root=Path(".")):
    return [json.loads(path.read_text()) for path in sorted(root.glob("custom_components/*/manifest.json"))]


def manifest_dependencies(root=Path(".")):
    """Home Assistant integrations the project depends on; their pip requirements get installed."""
    return sorted({name for data in manifests(root)
                   for name in (*data.get("dependencies", []), *data.get("after_dependencies", []))})


def manifest_requirements(root=Path(".")):
    """pip requirements the integration itself declares."""
    return [requirement for data in manifests(root) for requirement in data.get("requirements", [])]


def run(command, **options):
    options.setdefault("check", False)
    return subprocess.run(command, text=True, **options)


def prepare(release, domains, requirements):
    """Create the environment of one release unless it is complete already."""
    base = Path(os.environ.get("HASS_MATRIX_DIR", Path(tempfile.gettempdir()) / "hass-matrix"))
    folder, marker = base / release["homeassistant"], base / release["homeassistant"] / ".prepared"
    interpreter = folder / "bin" / "python"
    plugin_package = release.get("plugin_package", "pytest-homeassistant-custom-component")
    if plugin_package == "pytest-homeassistant":
        extras = sorted(set(domains) & {"bluetooth", "infrared", "radio_frequency"})
        if extras:
            plugin_package += "[" + ",".join(domain.replace("_", "-") for domain in extras) + "]"
    fingerprint = json.dumps({"release": release, "plugin_package": plugin_package,
                              "domains": domains, "requirements": requirements}, sort_keys=True)
    if marker.exists() and marker.read_text() == fingerprint:
        return interpreter
    run(["uv", "venv", "--python", release["python"], "--clear", str(folder)], check=True)
    plugin_requirement = f"{plugin_package}=={release['plugin']}"
    if "fixture_commit" in release:
        source = prepare_fixture_source(folder, release["fixture_commit"], release["homeassistant"])
        plugin_requirement = f"{plugin_package} @ {source.resolve().as_uri()}"
    install = ["uv", "pip", "install", "--python", str(interpreter)]
    if release.get("live"):
        if release.get("override_core"):
            print(f"Forward test: overriding the test plugin's Core pin with {release['homeassistant']}.",
                  file=sys.stderr)
        # Keep the selected Core installed during both dependency installations.
        override = folder / "core-override.txt"
        override.write_text(f"homeassistant=={release['homeassistant']}\n")
        install += ["--override", str(override)]
    # tzdata and setuptools are missing from the oldest environments but required by the plugin;
    # "pins" holds dependencies that later releases broke for a release's own requirements.
    legacy = [] if release.get("live") else ["setuptools<70"]
    run([*install, plugin_requirement,
         f"homeassistant=={release['homeassistant']}", "tzdata", *legacy,
         *release.get("pins", [])], check=True)
    needed = run([str(interpreter), "-c", COMPONENT_REQUIREMENTS, *domains],
                 capture_output=True, check=True).stdout.split("\n")
    needed = [item for item in (*needed, *requirements) if item]
    if needed:
        run([*install, *needed], check=True)
    run([str(interpreter), "-c", "import importlib.metadata,sys; "
         "assert importlib.metadata.version('homeassistant') == sys.argv[1]",
         release["homeassistant"]], check=True)
    marker.write_text(fingerprint)
    return interpreter


def prepare_fixture_source(folder, commit, version):
    """Build Core's matching test package when only its Core wheel reached PyPI."""
    import tomllib

    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Expected an immutable Core fixture commit")
    source = folder / "core-fixtures"
    source.mkdir()
    package = "packages/pytest-homeassistant"

    def git(*args):
        run(["git", *args], cwd=source, check=True)

    git("init", "--quiet")
    git("remote", "add", "origin", "https://github.com/home-assistant/core.git")
    git("fetch", "--quiet", "--depth=1", "--filter=blob:none", "origin", commit)
    git("restore", "--source", commit, "--worktree", "--", package, "packages/package_release.py", "pyproject.toml")
    run([sys.executable, "-m", "packages.package_release"], cwd=source, check=True)
    project = tomllib.loads((source / package / "pyproject.toml").read_text())["project"]
    if (project["name"] != "pytest-homeassistant" or project["version"] != version
            or f"homeassistant=={version}" not in project["dependencies"]):
        raise ValueError(f"Test package at {commit} does not match Core {version}")
    return source / package


def pytest_command(interpreter, directory, real):
    """The pytest call for one suite; the regular one keeps the Home Assistant plugin out."""
    command = [str(interpreter), "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    if real:
        # Core must initialize before pytest auto-loads plugins that import HTTPX.
        # Since 2026.11, Core aliases httpx2 and rejects an already imported httpx.
        return [str(interpreter), "-c",
                "import homeassistant; import pytest,sys; sys.exit(pytest.main(sys.argv[1:]))",
                "-q", "-p", "no:cacheprovider", "-p", "hass_real_tests",
                "-o", "asyncio_mode=auto", str(directory)]
    config = next((p for p in (Path(".github/dev/pyproject.toml"), Path("pyproject.toml")) if p.exists()), None)
    options = ["-c", str(config), "--rootdir", "."] if config else []
    return [*command, "-p", "no:homeassistant", "-p", "no:pytest_homeassistant",
            "-p", "no:respx", *options, str(directory)]


def test_release(release, domains, requirements):
    """Run the available suites; returns {suite name: passed}."""
    interpreter = prepare(release, domains, requirements)
    results = {}
    for name, directory, real in (("regular", REGULAR_TESTS, False), ("real", real_tests(), True)):
        if directory.is_dir():
            environment = {**os.environ, "PYTHONPATH": str(Path(__file__).parent)} if real else None
            outcome = run(pytest_command(interpreter, directory, real), capture_output=True, env=environment)
            results[name] = outcome.returncode == 0
            if not results[name]:
                print(outcome.stdout[-12000:], file=sys.stderr)
                print(outcome.stderr[-6000:], file=sys.stderr)
            elif outcome.stdout:
                print(outcome.stdout[-2000:], file=sys.stderr)
    return results


def main(arguments):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("list", "run"))
    parser.add_argument("selection", nargs="*", help="releases to run (default: all)")
    parser.add_argument("--minimum", default=None, help="lowest Home Assistant version (default: hacs.json)")
    parser.add_argument("--live", action="store_true", help="discover current stable and upcoming releases from PyPI")
    parser.add_argument("--stable-only", action="store_true", help="use the discovered stable release for publishing")
    parser.add_argument("--matrix", action="store_true", help="emit complete target objects for matrix.include")
    parser.add_argument("--target-json", help="run the exact target frozen by the discovery job")
    options = parser.parse_intermixed_args(arguments)
    minimum = options.minimum or supported_minimum(minimum_from_hacs())
    if options.stable_only and (not options.live or options.selection or options.target_json):
        parser.error("--stable-only requires --live without an explicit target")
    # The hub runs its historical baseline in ci.yml, including on fork pull requests.
    available = releases(minimum) if REAL_TESTS.is_dir() else []
    if options.live and real_tests().is_dir():
        from ha_discovery import discover
        targets = {item["homeassistant"]: item for item in available}
        for item in discover():
            if not minimum or version_key(item["homeassistant"]) >= version_key(minimum):
                targets[item["homeassistant"]] = item
        available = sorted(targets.values(), key=lambda item: version_key(item["homeassistant"]))
    if options.stable_only:
        available = [item for item in available if item.get("live") and not item["preview"]]
        if len(available) != 1:
            parser.error("no supported stable Home Assistant target")
    if options.target_json:
        if options.command != "run" or options.live or options.selection:
            parser.error("--target-json requires run without --live or positional releases")
        if not real_tests().is_dir():
            parser.error("frozen target requires a real Home Assistant test suite")
        available = [json.loads(options.target_json)]
    if options.command == "list":
        print(json.dumps(available if options.matrix else [item["homeassistant"] for item in available]))
        return 0
    chosen = [item for item in available if not options.selection or item["homeassistant"] in options.selection]
    unknown = set(options.selection) - {item["homeassistant"] for item in chosen}
    if unknown:
        sys.exit(f"No such release for this project: {sorted(unknown)}")
    domains, requirements, failed = manifest_dependencies(), manifest_requirements(), 0
    for release in chosen:
        results = test_release(release, domains, requirements)
        failed += not all(results.values())
        summary = "  ".join(f"{name}: {'ok' if passed else 'FAILED'}" for name, passed in results.items())
        print(f"Home Assistant {release['homeassistant']:<10} Python {release['python']:<5} {summary}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
