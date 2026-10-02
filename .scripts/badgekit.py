"""Build Shields.io badges and arrange them in thematic rows."""
import json
import re
from urllib.parse import quote, urlencode


STYLE = "flat"
COLORS = {
    "info": "1877A5",
    "ok": "157F71",
    "stable": "2F855A",
    "pre": "C27C0E",
    "accent": "7C3AED",
    "write": "B45309",
    "muted": "5B6770",
}
SUPPORT = [
    ("Buy Me a Coffee", "Support", "Buy Me a Coffee", "FFDD00", "buy-me-a-coffee", "black",
     "https://buymeacoffee.com/seb5594"),
    ("PayPal", "Support", "PayPal", "0070BA", "paypal", "white",
     "https://www.paypal.com/donate/?hosted_button_id=QMQPNRENXDN26"),
]
CATALOG_URL = "https://github.com/seb5594/Home-Assistant-Apps"
MOUNT_NAMES = {"all_addon_configs": "app configs", "addons": "local apps"}
STAGES = {"a": "alpha", "b": "beta", "rc": "release candidate"}


def _url(path, **params):
    return f"https://img.shields.io/{path}?" + urlencode(params, quote_via=quote)


def _wrap(alt, url, link):
    image = f"![{alt}]({url})"
    return f"[{image}]({link})" if link else image


def static(label, message, color="ok", link=None, logo=None):
    params = {"label": label, "message": message, "color": COLORS.get(color, color), "style": STYLE}
    if logo:
        params.update(logo=logo, logoColor="white")
    return _wrap(label, _url("static/v1", **params), link)


def github(metric, repo, label, link=None, suffix=""):
    """Live badge backed by the GitHub API, e.g. github('stars', 'owner/name', 'stars')."""
    return _wrap(label, _url(f"github/{metric}/{repo}{suffix}", label=label, style=STYLE), link)


def workflow(repo, filename, label, link=None):
    url = _url(f"github/actions/workflow/status/{repo}/{filename}",
               branch="main", label=label, style=STYLE)
    return _wrap(label, url, link)


def endpoint(repo, name, label):
    """Metric published by the pipeline to the repository's `badges` branch."""
    source = f"https://raw.githubusercontent.com/{repo}/badges/{name}.json"
    return _wrap(label, _url("endpoint", url=source, style=STYLE), None)


def support_badges():
    return [_wrap(label, _url("static/v1", label=left, message=right, color=color,
                              logo=logo, logoColor=logo_color, style=STYLE), link)
            for label, left, right, color, logo, logo_color, link in SUPPORT]


def render(rows):
    """One line per non-empty row inside a single paragraph; <br> keeps the line spacing tight."""
    return "<br>\n".join(" ".join(row) for row in rows if row)


def _mount_type(entry):
    return entry.split(":", 1)[0] if isinstance(entry, str) else entry.get("type", next(iter(entry)))


def _mount_readonly(entry):
    if isinstance(entry, str):
        return not entry.endswith(":rw")
    return entry.get("read_only", True)


def mount_badges(data):
    """Group folders by access mode: two badges instead of one per folder."""
    modes = {True: [], False: []}
    for entry in data.get("map", []):
        name = MOUNT_NAMES.get(_mount_type(entry), _mount_type(entry))
        if name not in modes[_mount_readonly(entry)]:
            modes[_mount_readonly(entry)].append(name)
    badges = []
    if modes[True]:
        badges.append(static("read-only", " · ".join(modes[True]), "ok"))
    if modes[False]:
        badges.append(static("read-write", " · ".join(modes[False]), "write"))
    if data.get("devices"):
        badges.append(static("local disks", "attached", "info"))
    return badges


def option_count(options):
    """Count leaf settings so nested option groups are not reported as one entry."""
    if isinstance(options, dict):
        return sum(option_count(value) for value in options.values())
    return 1


def install_badge():
    redirect = ("https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?"
                + urlencode({"repository_url": CATALOG_URL}, quote_via=quote))
    return static("Home Assistant", "Add app repository", "18BCF2", redirect, "homeassistant")


def community_row(repo, forks=0):
    """Stars, forks (only once somebody forked), issues and activity."""
    link = f"https://github.com/{repo}"
    row = [github("stars", repo, "stars", f"{link}/stargazers")]
    if forks:
        row.append(github("forks", repo, "forks", f"{link}/forks"))
    row += [github("issues", repo, "issues", f"{link}/issues"),
            github("last-commit", repo, "updated", f"{link}/commits/main")]
    return row


def app_rows(data, repo, folder, with_install=True, forks=0):
    link = f"https://github.com/{repo}"
    capabilities = [static("stage", data.get("stage", "stable"), "stable")]
    if data.get("ingress"):
        capabilities.append(static("ingress", "enabled", "accent"))
    if data.get("privileged"):
        capabilities.append(static("privileged", ", ".join(data["privileged"]), "write"))
    if data.get("apparmor") is False:
        capabilities.append(static("apparmor", "disabled", "write"))
    if data.get("options"):
        capabilities.append(static("options", str(option_count(data["options"])), "info"))
    return [
        [static("version", str(data["version"]), "info", f"{link}/releases"),
         github("release-date-pre", repo, "released", f"{link}/releases"),
         workflow(repo, "ci.yml", "build", f"{link}/actions/workflows/ci.yml")],
        community_row(repo, forks) + [endpoint(repo, "image-pulls", "image pulls")],
        [static("arch", " · ".join(data["arch"]), "ok")],
        mount_badges(data),
        capabilities,
        [endpoint(repo, "image-size", "image size"), endpoint(repo, "runtime-tests", "runtime tests"),
         endpoint(repo, "last-build", "last build")],
        [install_badge()] if with_install else [],
        support_badges() if with_install else [],
    ]


def stage_of(version):
    match = re.search(r"(a|b|rc)\d+$", version)
    return STAGES[match.group(1)] if match else "stable"


def integration_rows(manifest, hacs, repo, with_install=True, forks=0):
    link = f"https://github.com/{repo}"
    owner, name = repo.split("/")
    platform = [static("home assistant", f"≥ {hacs['homeassistant']}", "info")] \
        if hacs.get("homeassistant") else []
    platform += [static("stage", stage_of(manifest["version"]),
                        "stable" if stage_of(manifest["version"]) == "stable" else "pre"),
                 static("type", manifest.get("integration_type", "integration"), "muted"),
                 static("iot class", manifest.get("iot_class", "unknown").replace("_", " "), "muted")]
    if manifest.get("config_flow"):
        platform.append(static("setup", "UI config flow", "ok"))
    discovery = [key for key in ("bluetooth", "zeroconf", "ssdp", "dhcp", "usb", "mqtt")
                 if manifest.get(key)]
    if discovery:
        platform.append(static("discovery", ", ".join(discovery), "ok"))
    platform.append(static("requirements", str(len(manifest.get("requirements", []))), "info"))
    if manifest.get("quality_scale"):
        platform.append(static("quality scale", manifest["quality_scale"], "ok"))
    hacs_button = static("HACS", "Add integration", "41BDF5",
                         "https://my.home-assistant.io/redirect/hacs_repository/?"
                         + urlencode({"owner": owner, "repository": name, "category": "integration"},
                                     quote_via=quote), "homeassistantcommunitystore")
    return [
        [static("version", str(manifest["version"]), "info", f"{link}/releases"),
         github("release-date-pre", repo, "released", f"{link}/releases"),
         workflow(repo, "ci.yml", "checks", f"{link}/actions/workflows/ci.yml")],
        community_row(repo, forks),
        [github("downloads", repo, "downloads", f"{link}/releases", "/total"),
         github("downloads", repo, "latest release", f"{link}/releases/latest", "/latest/total")],
        platform,
        [endpoint(repo, "tests", "tests"), endpoint(repo, "zip-size", "HACS zip"),
         endpoint(repo, "last-build", "last build")],
        [hacs_button] if with_install else [],
        support_badges() if with_install else [],
    ]


def dump_endpoint(label, message, color="ok"):
    """Shields endpoint payload, see https://shields.io/badges/endpoint-badge."""
    return json.dumps({"schemaVersion": 1, "label": label, "message": message,
                       "color": COLORS.get(color, color), "cacheSeconds": 3600}, indent=2) + "\n"
