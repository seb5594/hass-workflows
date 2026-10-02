"""Names, URLs and constants shared by every engine script; change them here only."""
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]

OWNER = "seb5594"
USER_AGENT = f"{OWNER}-hass-workflows"

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

# (alt text, left label, right label, color, logo, logo color, link)
SUPPORT = [
    ("Buy Me a Coffee", "Support", "Buy Me a Coffee", "FFDD00", "buy-me-a-coffee", "black",
     f"https://buymeacoffee.com/{OWNER}"),
    ("PayPal", "Support", "PayPal", "0070BA", "paypal", "white",
     "https://www.paypal.com/donate/?hosted_button_id=QMQPNRENXDN26"),
]


def github_url(repository):
    return f"https://github.com/{repository}"
