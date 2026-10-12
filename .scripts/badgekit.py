"""Build Shields.io badges and arrange them in thematic rows."""
from urllib.parse import quote, urlencode

import config
import metrics


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
CATALOG_URL = config.github_url(config.APPS_CATALOG)
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


def support_badges():
    """Donation badges in the larger `for-the-badge` style so they stand out from the rest."""
    return [_wrap(label, _url("static/v1", label=left, message=right, color=color, logo=logo,
                              logoColor=logo_color, style="for-the-badge"), link)
            for label, left, right, color, logo, logo_color, link in config.SUPPORT]


SUPPORT_HEADING = "## Say thanks"
SUPPORT_TEXT = (
    "All my projects are built in my spare time, just for the fun of it. Still, they take a lot of time "
    "and care, and many of the smart home gadgets I buy end up here because I want to make them "
    "cloud-free and smart-home ready. Every bit of support means a lot to me.\n\n"
    "If my work helped you or turned out to be useful, show your appreciation with a hot drink for my "
    "next sleepless night.")


def support_section():
    """The shared thank-you block: heading, text and the donation badges."""
    return f"{SUPPORT_HEADING}\n\n{SUPPORT_TEXT}\n\n" + " ".join(support_badges())


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
    """One badge for all mounted folders, sorted; writable ones are marked, plus attached disks."""
    folders = {}
    for entry in data.get("map", []):
        folders.setdefault(MOUNT_NAMES.get(_mount_type(entry), _mount_type(entry)), _mount_readonly(entry))
    badges = []
    if folders:
        writable = [name for name, readonly in folders.items() if not readonly]
        names = sorted(folders, key=str.casefold)
        if not writable:
            label, color = "mounts (read-only)", "ok"
        elif len(writable) == len(folders):
            label, color = "mounts (read-write)", "write"
        else:
            label, color = "mounts", "write"
            names = [f"{name} (rw)" if name in writable else name for name in names]
        badges.append(static(label, " · ".join(names), color))
    if data.get("devices"):
        badges.append(static("local disks", "attached", "info"))
    return badges


def architecture_rank(arch):
    """Canonical order (amd64 first) instead of whatever order config.yaml lists."""
    return list(config.PLATFORMS).index(arch) if arch in config.PLATFORMS else len(config.PLATFORMS)


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
    ["image_pulls", "image_size", "runtime_tests"],
    ["stars", "forks", "issues", "updated"],
    ["arch"],
    ["mounts"],
    ["stage", "ingress", "privileged", "apparmor", "options"],
    ["install"],
]
INTEGRATION_LAYOUT = [
    ["install", "setup"],
    ["home_assistant", "version", "released", "checks", "compatibility", "quality_scale"],
    ["downloads", "latest_downloads", "zip_size", "tests"],
    ["stars", "forks", "issues", "updated"],
]
# Rows that only make sense on a project's own README, not in a catalog listing.
README_ONLY = {"install"}


def _links(ctx):
    return f"https://github.com/{ctx['repo']}"


def has(ctx, fact):
    """Live badges appear only with a value: zero, missing or unknown facts hide them.

    Without live facts (offline rendering) every badge is kept.
    """
    live = ctx.get("live")
    return True if live is None else bool(live.get(fact))


def released_more_than_once(ctx):
    """A separate 'latest release' counter only adds something next to an older release."""
    live = ctx.get("live")
    return True if live is None else live.get("releases", 0) > 1


def measured(ctx, key):
    """Display text of a pipeline measurement from .github/metrics.json; None when never measured."""
    snapshot = ctx.get("metrics") or {}
    return metrics.display(key, snapshot[key]) if key in snapshot else None


def measurement(ctx, key, label, color="ok", suffix=""):
    """Static badge for one measurement; nothing when the pipeline has not measured it yet."""
    value = measured(ctx, key)
    return [static(label, f"{value}{suffix}", color)] if value is not None else []


def image_sizes(ctx):
    """One compact badge, e.g. 'amd64 16.8 · aarch64 19.9 MiB', in canonical architecture order."""
    sizes = measured(ctx, "image_size")
    if not sizes:
        return []
    parts = [f"{arch} {sizes[arch].removesuffix(' MiB')}" for arch in sorted(sizes, key=architecture_rank)]
    return [static("image size", " · ".join(parts) + " MiB", "ok")]


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
        "image_pulls": lambda c: measurement(c, "image_pulls", "image pulls", "info"),
        "image_size": image_sizes,
        "runtime_tests": lambda c: measurement(c, "runtime_tests", "runtime tests", "stable", " passed"),
        "arch": lambda c: [static("arch", " · ".join(sorted(c["data"]["arch"], key=architecture_rank)), "ok")],
        "mounts": mounts,
        "stage": lambda c: [static("stage", c["data"].get("stage", "stable"), "stable")],
        "ingress": flag("ingress", lambda d: "enabled", "accent", lambda d: d.get("ingress")),
        "privileged": flag("privileged", lambda d: ", ".join(d["privileged"]), "write",
                           lambda d: d.get("privileged")),
        "apparmor": flag("apparmor", lambda d: "disabled", "write", lambda d: d.get("apparmor") is False),
        "options": flag("options", lambda d: str(option_count(d["options"])), "info",
                        lambda d: d.get("options")),
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
        # Release ZIP downloads are the closest thing to an install count GitHub offers; they are
        # shown from the first release on, even while the counter is still at zero.
        "downloads": lambda c: when(has(c, "releases"), [github(
            "downloads", c["repo"], "downloads", f"{_links(c)}/releases", "/total")]),
        "latest_downloads": lambda c: when(released_more_than_once(c), [github(
            "downloads", c["repo"], "latest release", f"{_links(c)}/releases/latest", "/latest/total")]),
        "compatibility": lambda c: when(c.get("compat") and has(c, "builds"), [workflow(
            c["repo"], "compat.yml", "HA releases", f"{_links(c)}/actions/workflows/compat.yml")]),
        "home_assistant": minimum_version,
        "setup": lambda c: [static("setup", "UI config flow", "ok")] if c["data"].get("config_flow") else [],
        "quality_scale": lambda c: [static("quality scale", c["data"]["quality_scale"], "ok")]
        if c["data"].get("quality_scale") else [],
        "tests": lambda c: measurement(c, "tests", "tests", "stable", " passed"),
        "zip_size": lambda c: measurement(c, "zip_size", "ZIP size", "ok"),
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


def app_rows(data, repo, folder, with_install=True, forks=0, live=None, measured_values=None):
    context = {"data": data, "repo": repo, "folder": folder, "forks": forks, "live": live,
               "metrics": measured_values}
    return build_rows(APP_LAYOUT, _app_builders(), context, with_install)


def integration_rows(manifest, hacs, repo, with_install=True, forks=0, live=None, measured_values=None,
                     compat=False):
    """`compat` marks projects that keep the Compatibility workflow (tests against real releases)."""
    context = {"data": manifest, "hacs": hacs, "repo": repo, "forks": forks, "live": live,
               "metrics": measured_values, "compat": compat}
    return build_rows(INTEGRATION_LAYOUT, _integration_builders(), context, with_install)

