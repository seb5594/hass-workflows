"""Build Shields.io badges and arrange them in thematic rows."""
import json
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


def hacs_badge(repo):
    owner, name = repo.split("/")
    redirect = ("https://my.home-assistant.io/redirect/hacs_repository/?"
                + urlencode({"owner": owner, "repository": name, "category": "integration"}, quote_via=quote))
    return static("HACS", "Add integration", "41BDF5", redirect, "homeassistantcommunitystore")


# ---------------------------------------------------------------------------------------------
# Badge layout: THE place to add, remove or reorder badges for every project and catalog.
# Each inner list is one line; each name refers to a builder below. Unknown names fail loudly,
# builders that have nothing to show simply return no badge.
# ---------------------------------------------------------------------------------------------
APP_LAYOUT = [
    ["version", "released", "build"],
    ["stars", "forks", "issues", "updated", "license", "image_pulls"],
    ["arch"],
    ["mounts"],
    ["stage", "ingress", "privileged", "apparmor", "options"],
    ["image_size", "runtime_tests", "last_build"],
    ["install"],
    ["support"],
]
INTEGRATION_LAYOUT = [
    ["install", "setup"],
    ["home_assistant", "version", "released", "checks", "quality_scale"],
    ["downloads", "latest_downloads"],
    ["stars", "forks", "issues", "updated", "license"],
    ["tests", "zip_size", "last_build"],
    ["support"],
]
# Rows that only make sense on a project's own README, not in a catalog listing.
README_ONLY = {"install", "support"}


def _links(ctx):
    return f"https://github.com/{ctx['repo']}"


def has(ctx, fact):
    """Live badges appear only with a value: zero, missing or unknown facts hide them.

    Without live facts (offline rendering) every badge is kept.
    """
    live = ctx.get("live")
    return True if live is None else bool(live.get(fact))


def published(ctx, metric):
    """Endpoint badges exist only after the pipeline published their JSON file."""
    live = ctx.get("live")
    return True if live is None else metric in live["metrics"]


def licensed(ctx):
    """A license badge needs a confirmed license, so it stays hidden when facts are unknown."""
    live = ctx.get("live")
    return bool(live and live.get("license"))


def when(condition, badges):
    return badges if condition else []


def _common_builders():
    return {
        "version": lambda c: [static("version", str(c["data"]["version"]), "info", f"{_links(c)}/releases")],
        "released": lambda c: when(has(c, "releases"),
                                   [github("release-date-pre", c["repo"], "released", f"{_links(c)}/releases")]),
        "stars": lambda c: when(has(c, "stars"),
                                [github("stars", c["repo"], "stars", f"{_links(c)}/stargazers")]),
        "forks": lambda c: when(has(c, "forks") if c.get("live") else c["forks"],
                                [github("forks", c["repo"], "forks", f"{_links(c)}/forks")]),
        "issues": lambda c: when(has(c, "issues"),
                                 [github("issues", c["repo"], "issues", f"{_links(c)}/issues")]),
        "updated": lambda c: [github("last-commit", c["repo"], "updated", f"{_links(c)}/commits/main")],
        "license": lambda c: when(licensed(c), [github("license", c["repo"], "license", _links(c))]),
        "last_build": lambda c: when(published(c, "last-build"), [endpoint(c["repo"], "last-build", "last build")]),
        "support": lambda c: support_badges(),
    }


def _app_builders():
    def mounts(c):
        return mount_badges(c["data"])

    def flag(label, value, color, condition):
        return lambda c: [static(label, value(c["data"]), color)] if condition(c["data"]) else []

    builders = _common_builders()
    builders.update({
        "build": lambda c: when(has(c, "builds"), [workflow(
            c["repo"], "ci.yml", "build", f"{_links(c)}/actions/workflows/ci.yml")]),
        "image_pulls": lambda c: when(published(c, "image-pulls"), [endpoint(c["repo"], "image-pulls", "image pulls")]),
        "arch": lambda c: [static("arch", " · ".join(c["data"]["arch"]), "ok")],
        "mounts": mounts,
        "stage": lambda c: [static("stage", c["data"].get("stage", "stable"), "stable")],
        "ingress": flag("ingress", lambda d: "enabled", "accent", lambda d: d.get("ingress")),
        "privileged": flag("privileged", lambda d: ", ".join(d["privileged"]), "write",
                           lambda d: d.get("privileged")),
        "apparmor": flag("apparmor", lambda d: "disabled", "write", lambda d: d.get("apparmor") is False),
        "options": flag("options", lambda d: str(option_count(d["options"])), "info",
                        lambda d: d.get("options")),
        "image_size": lambda c: when(published(c, "image-size"), [endpoint(c["repo"], "image-size", "image size")]),
        "runtime_tests": lambda c: when(published(c, "runtime-tests"),
                                        [endpoint(c["repo"], "runtime-tests", "runtime tests")]),
        "install": lambda c: [install_badge()],
    })
    return builders


def _integration_builders():
    def minimum_version(c):
        minimum = c["hacs"].get("homeassistant")
        return [static("home assistant", f"≥ {minimum}", "info")] if minimum else []

    builders = _common_builders()
    builders.update({
        "checks": lambda c: when(has(c, "builds"), [workflow(
            c["repo"], "ci.yml", "checks", f"{_links(c)}/actions/workflows/ci.yml")]),
        "downloads": lambda c: when(has(c, "downloads"), [github(
            "downloads", c["repo"], "downloads", f"{_links(c)}/releases", "/total")]),
        "latest_downloads": lambda c: when(has(c, "latest_downloads"), [github(
            "downloads", c["repo"], "latest release", f"{_links(c)}/releases/latest", "/latest/total")]),
        "home_assistant": minimum_version,
        "setup": lambda c: [static("setup", "UI config flow", "ok")] if c["data"].get("config_flow") else [],
        "quality_scale": lambda c: [static("quality scale", c["data"]["quality_scale"], "ok")]
        if c["data"].get("quality_scale") else [],
        "tests": lambda c: when(published(c, "tests"), [endpoint(c["repo"], "tests", "tests")]),
        "zip_size": lambda c: when(published(c, "zip-size"), [endpoint(c["repo"], "zip-size", "HACS zip")]),
        "install": lambda c: [hacs_badge(c["repo"])],
    })
    return builders


def build_rows(layout, builders, context, with_install=True):
    rows = []
    for names in layout:
        row = []
        for name in names:
            if name in README_ONLY and not with_install:
                continue
            row += builders[name](context)
        rows.append(row)
    return rows


def app_rows(data, repo, folder, with_install=True, forks=0, live=None):
    context = {"data": data, "repo": repo, "folder": folder, "forks": forks, "live": live}
    return build_rows(APP_LAYOUT, _app_builders(), context, with_install)


def integration_rows(manifest, hacs, repo, with_install=True, forks=0, live=None):
    context = {"data": manifest, "hacs": hacs, "repo": repo, "forks": forks, "live": live}
    return build_rows(INTEGRATION_LAYOUT, _integration_builders(), context, with_install)


def dump_endpoint(label, message, color="ok"):
    """Shields endpoint payload, see https://shields.io/badges/endpoint-badge."""
    return json.dumps({"schemaVersion": 1, "label": label, "message": message,
                       "color": COLORS.get(color, color), "cacheSeconds": 3600}, indent=2) + "\n"
