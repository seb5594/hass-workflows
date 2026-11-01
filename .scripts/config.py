"""Names, URLs and constants shared by every engine script; change them here only."""
import os
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]

OWNER = "seb5594"
USER_AGENT = f"{OWNER}-hass-workflows"

# The default branch of the repository the workflow runs for (the action passes it in); badges and
# picture links in the README point to it. Local runs fall back to "main".
DEFAULT_BRANCH = os.environ.get("DEFAULT_BRANCH") or "main"

ENGINE_REPOSITORY = f"{OWNER}/hass-workflows"
APPS_CATALOG = f"{OWNER}/Home-Assistant-Apps"
INTEGRATIONS_CATALOG = f"{OWNER}/Home-Assistant-Integrations"
HUB_REPOSITORY = f"{OWNER}/Home-Assistant-Hub"
CATALOGS = {"apps": APPS_CATALOG, "integrations": INTEGRATIONS_CATALOG}

# Supported architectures in display order, mapped to their Docker platform.
PLATFORMS = {
    "amd64": "linux/amd64",
    "aarch64": "linux/arm64",
    "armv7": "linux/arm/v7",
    "armhf": "linux/arm/v6",
    "i386": "linux/386",
}

# The current Home Assistant base image ships amd64 and aarch64 only. These architectures exist
# solely as the previous generation of per-architecture base images; see legacy.py.
LEGACY_ARCHES = ("armv7", "armhf", "i386")
LEGACY_BASE = "ghcr.io/home-assistant/{arch}-base:3.22-2025.11.1"

# repository_dispatch events that tell a catalog or the hub to refresh.
EVENTS = {"apps": "update-addons", "integrations": "update-integrations", "hub": "update-hub"}

# Every repository the engine serves, by catalog kind. Drives the engine's own validation matrix.
PROJECTS = {
    "apps": ["Home-Assistant-Rsync-Local-Addon", "Home-Assistant-Git-Exporter-Addon",
             "Home-Assistant-Playstation-VR-Camera-Loader-App", "Home-Assistant-UnTuyaOS3-App",
             "Home-Assistant-WiFi-Helper-App", "Home-Assistant-Tuya-Breaker-App",
             "Home-Assistant-Gitea-MCP-Server-App", "Home-Assistant-Gitea-Runner-App",
             "Home-Assistant-Gitea-Mirror-App", "Home-Assistant-Assist-AI-Router-App",
             "Home-Assistant-App-Template"],
    "integrations": ["hass-ninebot_e_scooters-integration", "hass-pulseaudio_loopback_extended-integration",
                     "hass-vacuum_mapguard-integration", "hass-medication_tracker-integration",
                     "Home-Assistant-Integration-Template"],
}

# Donation channels, defined once: README badges and .github/FUNDING.yml are both built from them.
COFFEE_USER = OWNER
PAYPAL_URL = f"https://paypal.me/{OWNER}"
COFFEE_URL = f"https://buymeacoffee.com/{COFFEE_USER}"
# name -> (alt text, left label, right label, color, logo, logo color, link), in display order
SUPPORT = {
    "paypal": ("PayPal", "Support", "PayPal", "0070BA", "paypal", "white", PAYPAL_URL),
    "coffee": ("Buy Me a Coffee", "Support", "Buy Me a Coffee", "FFDD00", "buy-me-a-coffee", "black", COFFEE_URL),
}


def github_url(repository):
    return f"https://github.com/{repository}"
