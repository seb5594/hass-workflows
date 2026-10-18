"""Build Shields.io badges and arrange them in rows of three sizes."""
import html
from dataclasses import dataclass
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


@dataclass(frozen=True)
class Tier:
    """How large a row of badges is drawn: the Shields style and the rendered height in pixels."""
    style: str
    height: int


# The smallest tier keeps the native height of a flat badge; the others are 2x and 1.4x of it.
HERO = Tier("for-the-badge", 40)
MAJOR = Tier("for-the-badge", 28)
MINOR = Tier(STYLE, 20)


@dataclass(frozen=True)
class Badge:
    """One Shields badge; the style is chosen when it is rendered, so a row decides its own size."""
    alt: str
    path: str
    params: dict
    link: str | None = None

    def url(self, style=STYLE):
        return f"https://img.shields.io/{self.path}?" + urlencode({**self.params, "style": style}, quote_via=quote)

    def markdown(self, style=STYLE):
        image = f"![{self.alt}]({self.url(style)})"
        return f"[{image}]({self.link})" if self.link else image

    def html(self, tier):
        image = f'<img src="{html.escape(self.url(tier.style))}" alt="{html.escape(self.alt)}" height="{tier.height}">'
        return f'<a href="{html.escape(self.link)}">{image}</a>' if self.link else image

    __str__ = markdown


@dataclass(frozen=True)
class Row:
    tier: Tier
    badges: list


def static(label, message, color="ok", link=None, logo=None, logo_color="white"):
    params = {"label": label, "message": message, "color": COLORS.get(color, color)}
    if logo:
        params.update(logo=logo, logoColor=logo_color)
    return Badge(label, "static/v1", params, link)


def github(metric, repo, label, link=None, suffix="", color=None):
    """Live badge backed by the GitHub API, e.g. github('stars', 'owner/name', 'stars').

    `color` overrides Shields' own choice, which paints a zero download counter red as if
    something were broken.
    """
    params = {"label": label}
    if color:
        params["color"] = COLORS.get(color, color)
    return Badge(label, f"github/{metric}/{repo}{suffix}", params, link)


def workflow(repo, filename, label, link=None):
    return Badge(label, f"github/actions/workflow/status/{repo}/{filename}",
                 {"branch": config.DEFAULT_BRANCH, "label": label}, link)


def support_badge(name):
    alt, left, right, color, logo, logo_color, link = config.SUPPORT[name]
    return static(left, right, color, link, logo, logo_color)


def support_badges():
    return [support_badge(name) for name in config.SUPPORT]


SUPPORT_HEADING = "## Say thanks"
SUPPORT_TEXT = (
    "All my projects are built in my spare time, just for the fun of it. Still, they take a lot of time "
    "and care, and many of the smart home gadgets I buy end up here because I want to make them "
    "cloud-free and smart-home ready. Every bit of support means a lot to me.\n\n"
    "If my work helped you or turned out to be useful, show your appreciation with a hot drink for my "
    "next sleepless night.")


def support_section():
    """The shared thank-you block: heading, text and the donation badges in the large style."""
    return (f"{SUPPORT_HEADING}\n\n{SUPPORT_TEXT}\n\n"
            + " ".join(badge.markdown(HERO.style) for badge in support_badges()))


def render(rows):
    """Compact catalog form: one line per non-empty list of badges inside a single paragraph."""
    return "<br>\n".join(" ".join(str(badge) for badge in row) for row in rows if row)


def render_header(rows):
    """Centered README form: one paragraph per row, drawn in the size of the row's tier."""
    return "\n\n".join(
        '<p align="center">\n  ' + "\n  ".join(badge.html(row.tier) for badge in row.badges) + "\n</p>"
        for row in rows if row.badges)


def plain(rows):
    """The badge lists of rows, for places that ignore the tiers."""
    return [row.badges for row in rows]


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
# Each entry is one row: its size and the names of its badges, each naming a builder below.
# Unknown names fail loudly; builders that have nothing to show simply return no badge.
# ---------------------------------------------------------------------------------------------
INTEGRATION_LAYOUT = [
    (HERO, ["paypal", "coffee"]),
    (MAJOR, ["install", "home_assistant", "version", "downloads"]),
    (MINOR, ["stars", "issues", "tests", "checks", "license"]),
]
APP_LAYOUT = [
    (HERO, ["paypal", "coffee"]),
    (MAJOR, ["install", "home_assistant", "version", "image_pulls"]),
    (MINOR, ["stars", "issues", "runtime_tests", "checks", "license"]),
    (MINOR, ["arch", "mounts", "stage", "ingress", "privileged", "apparmor", "options", "image_size"]),
]
# Badges that only make sense in a project's own README, not in a catalog listing. The catalog
# names its licenses in one closing note instead of a badge per entry.
README_ONLY = {"paypal", "coffee", "install", "license"}


def _links(ctx):
    return config.github_url(ctx["repo"])


def has(ctx, fact):
    """Live badges appear only with a value: zero, missing or unknown facts hide them.

    Without live facts (offline rendering) every badge is kept.
    """
    live = ctx.get("live")
    return True if live is None else bool(live.get(fact))


def has_license(ctx):
    """GitHub's detection decides when it is asked; offline, the license file of the checkout does."""
    live = ctx.get("live")
    if live is None:
        return bool(ctx.get("licensed"))
    return live.get("license") not in (None, "", "NOASSERTION")


def latest_tag(ctx):
    """Tag of the newest published release; None before the first release or without live facts."""
    return (ctx.get("live") or {}).get("latest_tag")


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


def version(ctx):
    """The newest release; before the first one (or offline) the version the metadata declares."""
    tag = latest_tag(ctx)
    shown = tag.removeprefix("v") if tag else str(ctx["data"]["version"])
    return [static("version", shown, "info", f"{_links(ctx)}/releases/tag/{tag}" if tag else f"{_links(ctx)}/releases")]


def downloads(ctx):
    """Release asset downloads of the newest release. Shown from the first release on, at zero too."""
    tag = latest_tag(ctx)
    path = f"/{quote(tag, safe='')}/total" if tag else "/latest/total"
    return when(has(ctx, "releases"), [github(
        "downloads", ctx["repo"], "downloads", f"{_links(ctx)}/releases", path, "info")])


def home_assistant(ctx):
    """Lowest supported Home Assistant version; a Compatibility workflow, when kept, proves it."""
    minimum = ctx.get("minimum")
    link = f"{_links(ctx)}/actions/workflows/compat.yml" if ctx.get("compat") else None
    return [static("home assistant", f"≥ {minimum}", "info", link)] if minimum else []


def _common_builders():
    return {
        "paypal": lambda c: [support_badge("paypal")],
        "coffee": lambda c: [support_badge("coffee")],
        "home_assistant": home_assistant,
        "version": version,
        "stars": lambda c: when(has(c, "stars"),
                                [github("stars", c["repo"], "stars", f"{_links(c)}/stargazers")]),
        "issues": lambda c: [github("issues", c["repo"], "issues", f"{_links(c)}/issues")],
        "checks": lambda c: when(has(c, "builds"), [workflow(
            c["repo"], "ci.yml", "checks", f"{_links(c)}/actions/workflows/ci.yml")]),
        "license": lambda c: when(has_license(c), [github("license", c["repo"], "license", f"{_links(c)}#license")]),
    }


def _app_builders():
    def flag(label, value, color, condition):
        return lambda c: [static(label, value(c["data"]), color)] if condition(c["data"]) else []

    builders = _common_builders()
    builders.update({
        "install": lambda c: [install_badge()],
        "image_pulls": lambda c: measurement(c, "image_pulls", "image pulls", "info"),
        "image_size": image_sizes,
        "runtime_tests": lambda c: measurement(c, "runtime_tests", "runtime tests", "stable", " passed"),
        "arch": lambda c: [static("arch", " · ".join(sorted(c["data"]["arch"], key=architecture_rank)), "ok")],
        "mounts": lambda c: mount_badges(c["data"]),
        "stage": lambda c: [static("stage", c["data"].get("stage", "stable"), "stable")],
        "ingress": flag("ingress", lambda d: "enabled", "accent", lambda d: d.get("ingress")),
        "privileged": flag("privileged", lambda d: ", ".join(d["privileged"]), "write",
                           lambda d: d.get("privileged")),
        "apparmor": flag("apparmor", lambda d: "disabled", "write", lambda d: d.get("apparmor") is False),
        "options": flag("options", lambda d: str(option_count(d["options"])), "info",
                        lambda d: d.get("options")),
    })
    return builders


def _integration_builders():
    builders = _common_builders()
    builders.update({
        "install": lambda c: [hacs_badge(c["repo"])],
        "downloads": downloads,
        "tests": lambda c: measurement(c, "tests", "tests", "stable", " passed"),
    })
    return builders


def build_rows(layout, builders, context, standalone=True):
    """Rows of badges for a layout; a catalog listing (`standalone=False`) skips README-only badges."""
    rows = []
    for tier, names in layout:
        badges = []
        for name in names:
            if name in README_ONLY and not standalone:
                continue
            badges += builders[name](context)
        rows.append(Row(tier, badges))
    return rows


def app_rows(data, repo, standalone=True, live=None, measured_values=None, licensed=False):
    context = {"data": data, "repo": repo, "live": live, "metrics": measured_values, "licensed": licensed,
               "minimum": data.get("homeassistant")}
    return build_rows(APP_LAYOUT, _app_builders(), context, standalone)


def integration_rows(manifest, hacs, repo, standalone=True, live=None, measured_values=None, compat=False,
                     licensed=False):
    """`compat` marks projects that keep the Compatibility workflow (tests against real releases)."""
    context = {"data": manifest, "repo": repo, "live": live, "metrics": measured_values, "compat": compat,
               "licensed": licensed, "minimum": hacs.get("homeassistant")}
    return build_rows(INTEGRATION_LAYOUT, _integration_builders(), context, standalone)
