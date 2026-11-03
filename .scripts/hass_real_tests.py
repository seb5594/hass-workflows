"""pytest plugin for tests against a real Home Assistant core; ha_matrix.py loads it with -p.

It provides what every integration's real tests need, so they only add their own doubles:
custom_components of the repository is discoverable, and the integrations named in the
manifest's dependencies count as loaded (they would otherwise be set up with real hardware).
The core is booted for every test, so a test asks for `hass` only to use it.
"""
import importlib
import json
import sys

import pytest


def manifest_dependencies(root):
    """Dependencies declared by the integrations in root/custom_components."""
    names = set()
    for manifest in root.glob("custom_components/*/manifest.json"):
        data = json.loads(manifest.read_text())
        names.update(data.get("dependencies", []))
    return names


def expose_custom_components(root):
    """Older pytest-homeassistant-custom-component releases ship their own custom_components
    package, which would hide the repository's one; make it search both."""
    sys.path.insert(0, str(root))
    package = importlib.import_module("custom_components")
    folder = str(root / "custom_components")
    if folder not in package.__path__:
        package.__path__.append(folder)


def pytest_configure(config):
    expose_custom_components(config.rootpath)


@pytest.fixture(scope="session", autouse=True)
def _start_dns_helper_thread_early():
    """pycares 5 starts one background thread for the whole process when the first resolver appears.
    Home Assistant releases from before it existed count such a thread as left over by whichever
    test happens to create it, so create it before any test is measured."""
    try:
        import pycares

        pycares.Channel()
    except Exception:  # noqa: BLE001 - older pycares releases need no warm-up
        pass


@pytest.fixture(autouse=True)
def _real_home_assistant(verify_cleanup, enable_custom_integrations, hass, pytestconfig):
    """Boot the core for every test, with the repository's integrations and declared dependencies.

    Asking for verify_cleanup first keeps it set up before the core and so checked after the
    core has stopped; otherwise threads that Home Assistant is still joining count as stray.
    """
    hass.config.components.update(manifest_dependencies(pytestconfig.rootpath))
