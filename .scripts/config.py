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
DASHBOARDS_CATALOG = f"{OWNER}/Home-Assistant-Dashboards"
HUB_REPOSITORY = f"{OWNER}/Home-Assistant-Hub"
CATALOGS = {"apps": APPS_CATALOG, "integrations": INTEGRATIONS_CATALOG, "dashboards": DASHBOARDS_CATALOG}

# Source repositories of each catalog kind are recognised by name; `project` becomes the folder name.
# Dashboards are cards, themes and whatever else is shown in Lovelace: `Home-Assistant-<Project>-Card`,
# `-Lovelace-Card`, `-Dashboard` or `-Theme` (a `-Lovelace` before the suffix is not part of the project name).
NAME_PATTERNS = {
    "apps": r"^Home-Assistant-(?P<project>[A-Za-z0-9][A-Za-z0-9._-]*)-(?:Apps?|Addon)$",
    "integrations": r"^(?i:hass|Home-Assistant)-(?P<project>[A-Za-z0-9][A-Za-z0-9._-]*)-(?i:integration)$",
    "dashboards": r"^(?i:hass|Home-Assistant)-(?P<project>[A-Za-z0-9][A-Za-z0-9._-]*?)(?:-Lovelace)?-(?i:card|dashboard|theme)$",
}

# Kinds without a catalog repository yet. The hub lists their public repositories directly until
# the catalog exists and publishes `.github/catalog.json`.
UNCATALOGUED = {"dashboards"}

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
EVENTS = {"apps": "update-addons", "integrations": "update-integrations",
          "dashboards": "update-dashboards", "hub": "update-hub"}

# Every repository the engine serves, by catalog kind. Drives the engine's own validation matrix.
PROJECTS = {
    "apps": ["Home-Assistant-Rsync-Local-Addon", "Home-Assistant-Git-Exporter-Addon",
             "Home-Assistant-Playstation-VR-Camera-Loader-App", "Home-Assistant-UnTuyaOS3-App",
             "Home-Assistant-WiFi-Helper-App", "Home-Assistant-Tuya-Breaker-App",
             "Home-Assistant-Gitea-MCP-Server-App", "Home-Assistant-Gitea-Runner-App",
             "Home-Assistant-Gitea-Mirror-App", "Home-Assistant-Assist-AI-Router-App",
             "Home-Assistant-Extended-Secrets-App", "Home-Assistant-Docker-Socket-Proxy-App",
             "Home-Assistant-App-Template"],
    "integrations": ["hass-ninebot_e_scooters-integration", "hass-pulseaudio_loopback_extended-integration",
                     "hass-vacuum_mapguard-integration", "hass-medication_tracker-integration",
                     "Home-Assistant-Integration-Template", "hass-deepl_translator-integration",
                     "hass-custom_integrations_translator-integration",
                     "hass-ubpet_cat_litter_hub-integration", "hass-extended_secrets-integration",
                     "hass-perdis_roster-integration", "hass-pwa_app_studio-integration"],
    "dashboards": ["Home-Assistant-Config-Entry-Lovelace-Card"],
}

# Integrations that are never offered to the official HACS default catalog, with the reason.
# Everything else gets the manual "Marketplace catalog" workflow; catalogs and the hub never do.
DEFAULT_CATALOG_EXCLUDED = {
    "Home-Assistant-Integration-Template": "template repository",
    "hass-pulseaudio_loopback_extended-integration": "its domain replaces a Core integration",
}

# Donation channels, defined once: README badges and .github/FUNDING.yml are both built from them.
COFFEE_USER = OWNER
PAYPAL_URL = f"https://paypal.me/{OWNER}"
COFFEE_URL = f"https://buymeacoffee.com/{COFFEE_USER}"
BEER_BADGE_URL = "https://raw.githubusercontent.com/seb5594/Home-Assistant-Apps/473dc258f963096745aac327df54950eb9b59066/.github/assets/support-beer.svg"
# name -> (alt text, left label, right label, color, logo, logo color, link), in display order
SUPPORT = {
    "paypal": ("PayPal", "Support", "PayPal", "0070BA", "paypal", "white", PAYPAL_URL),
    "beer": ("Buy me a beer", "Support \U0001F37A", "Buy me a beer", "FFDD00", None, "black", COFFEE_URL),
}


def github_url(repository):
    return f"https://github.com/{repository}"

# Integration release tags without the conventional v prefix, as requested by their owner.
INTEGRATION_TAG_PREFIXES = {
    "seb5594/hass-google_translator-integration": "",
    "seb5594/hass-car_tires_season-integration": "",
    "seb5594/hass-medication_monitoring-integration": "",
    "seb5594/hass-deepl_translator-integration": "",
    "seb5594/hass-ubpet_cat_litter_hub-integration": "",
}

# These integrations publish after a separately validated version tag is pushed.
INTEGRATION_TAG_ONLY_RELEASES = {"seb5594/hass-ubpet_cat_litter_hub-integration"}
