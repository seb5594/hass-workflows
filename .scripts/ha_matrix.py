#!/usr/bin/env python3
"""Run a project's tests against genuine Home Assistant releases.

Each release gets its own virtual environment (made with uv) holding that Home
Assistant and the matching pytest-homeassistant-custom-component. Two suites run
in it, when the project has them:

* .github/tests     the regular suite, with the Home Assistant pytest plugin switched off
* .github/ha_tests  tests against a real Home Assistant core

The releases come from ha_releases.json; only those at or above the project's
minimum in hacs.json are used.

CLI:
    ha_matrix.py list [--minimum VERSION]    JSON list of releases (for a CI matrix)
    ha_matrix.py run [RELEASE ...]           test the given releases (default: all of them)
Environment: HASS_MATRIX_DIR keeps the virtual environments between runs.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

RELEASES = Path(__file__).with_name("ha_releases.json")
REGULAR_TESTS = Path(".github/tests")
REAL_TESTS = Path(".github/ha_tests")

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
    return tuple(int(part) for part in version.split("."))


def minimum_from_hacs(root=Path(".")):
    """The `homeassistant` minimum of hacs.json, or None when the project names none."""
    hacs = root / "hacs.json"
    return json.loads(hacs.read_text()).get("homeassistant") if hacs.exists() else None


def releases(minimum=None):
    """Known releases at or above `minimum`, oldest first."""
    table = json.loads(RELEASES.read_text())
    if minimum:
        table = [item for item in table if version_key(item["homeassistant"]) >= version_key(minimum)]
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
    if marker.exists():
        return interpreter
    run(["uv", "venv", "--python", release["python"], "--clear", str(folder)], check=True)
    install = ["uv", "pip", "install", "--python", str(interpreter)]
    # tzdata and setuptools are missing from the oldest environments but required by the plugin;
    # "pins" holds dependencies that later releases broke for a release's own requirements.
    run([*install, f"pytest-homeassistant-custom-component=={release['plugin']}",
         "tzdata", "setuptools<70", *release.get("pins", [])], check=True)
    needed = run([str(interpreter), "-c", COMPONENT_REQUIREMENTS, *domains],
                 capture_output=True, check=True).stdout.split("\n")
    needed = [item for item in (*needed, *requirements) if item]
    if needed:
        run([*install, *needed], check=True)
    marker.touch()
    return interpreter


def pytest_command(interpreter, directory, real):
    """The pytest call for one suite; the regular one keeps the Home Assistant plugin out."""
    command = [str(interpreter), "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    if real:
        return [*command, "-p", "hass_real_tests", "-o", "asyncio_mode=auto", str(directory)]
    config = next((p for p in (Path(".github/dev/pyproject.toml"), Path("pyproject.toml")) if p.exists()), None)
    options = ["-c", str(config), "--rootdir", "."] if config else []
    return [*command, "-p", "no:homeassistant", *options, str(directory)]


def test_release(release, domains, requirements):
    """Run the available suites; returns {suite name: passed}."""
    interpreter = prepare(release, domains, requirements)
    results = {}
    for name, directory, real in (("regular", REGULAR_TESTS, False), ("real", REAL_TESTS, True)):
        if directory.is_dir():
            environment = {**os.environ, "PYTHONPATH": str(Path(__file__).parent)} if real else None
            outcome = run(pytest_command(interpreter, directory, real), capture_output=True, env=environment)
            results[name] = outcome.returncode == 0
            if not results[name]:
                print(outcome.stdout[-6000:], file=sys.stderr)
    return results


def main(arguments):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("list", "run"))
    parser.add_argument("selection", nargs="*", help="releases to run (default: all)")
    parser.add_argument("--minimum", default=None, help="lowest Home Assistant version (default: hacs.json)")
    options = parser.parse_intermixed_args(arguments)
    minimum = options.minimum or minimum_from_hacs()
    available = releases(minimum) if REAL_TESTS.is_dir() else []
    if options.command == "list":
        print(json.dumps([item["homeassistant"] for item in available]))
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
