"""Build Shields.io badges and arrange them in rows of three sizes."""
import html
from dataclasses import dataclass, replace
from urllib.parse import quote, urlencode

import config
import metrics
from common import is_prerelease, release_title


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


# The smallest tier keeps the native height of a flat badge; the others are 1.4x and 1.2x of it.
MAJOR = Tier("for-the-badge", 28)
SUPPORT = Tier("for-the-badge", 24)  # smaller than the facts above it: the two donation badges stay
MINOR = Tier(STYLE, 20)             # side by side on desktop and simply wrap on a phone


@dataclass(frozen=True)
class Badge:
    """One Shields badge; the style is chosen when it is rendered, so a row decides its own size."""
    alt: str
    path: str
    params: dict
    link: str | None = None
    source: str | None = None

    def url(self, style=STYLE):
        if self.source:
            return self.source
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


def workflow(repo, filename, label, link=None, branch=None):
    return Badge(label, f"github/actions/workflow/status/{repo}/{filename}",
                 {"branch": branch or config.DEFAULT_BRANCH, "label": label}, link)


def support_badge(name):
    alt, left, right, color, logo, logo_color, link = config.SUPPORT[name]
    return replace(static(left, right, color, link, logo, logo_color), alt=alt,
                   source=config.BEER_BADGE_URL if name == "beer" else None)


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
            + " ".join(badge.markdown(MAJOR.style) for badge in support_badges()))


def render(rows):
    """Compact catalog form: one line per non-empty list of badges inside a single paragraph."""
    return "<br>\n".join(" ".join(str(badge) for badge in row) for row in rows if row)


def render_header(rows):
    """Centered README form: all rows in one paragraph, each drawn in the size of its tier.

    One paragraph with line breaks keeps the rows close together; separate paragraphs would add
    the full paragraph margin between them.
    """
    lines = ["\n  ".join(badge.html(row.tier) for badge in row.badges) for row in rows if row.badges]
    return '<p align="center">\n  ' + "<br>\n  ".join(lines) + "\n</p>" if lines else ""


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


def install_badge():
    redirect = ("https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?"
                + urlencode({"repository_url": CATALOG_URL}, quote_via=quote))
    return static("Home Assistant", "Add app repository", "18BCF2", redirect, "homeassistant")


INSTALL_LABEL = "HACS · Marketplace"


def hacs_badge(repo):
    """Install badge for HACS (Home Assistant up to 2026.10) and the Marketplace (2026.11 and newer).

    The link deliberately keeps the `hacs_repository` redirect: the Marketplace accepts it with the same
    parameters, while the newer `marketplace_repository` redirect does not exist on older instances.
    """
    owner, name = repo.split("/")
    redirect = ("https://my.home-assistant.io/redirect/hacs_repository/?"
                + urlencode({"owner": owner, "repository": name, "category": "integration"}, quote_via=quote))
    return static(INSTALL_LABEL, "Add integration", "41BDF5", redirect, "homeassistantcommunitystore")


# ---------------------------------------------------------------------------------------------
# Badge layout: THE place to add, remove or reorder badges for every project and catalog.
# Each entry is one row: its size and the names of its badges, each naming a builder below.
# Unknown names fail loudly; builders that have nothing to show simply return no badge.
# ---------------------------------------------------------------------------------------------
INTEGRATION_LAYOUT = [
    (MAJOR, ["install", "home_assistant"]),
    (MAJOR, ["version", "downloads"]),
    (MINOR, ["stars", "forks", "checks", "tests", "issues"]),
    (SUPPORT, ["paypal", "beer"]),
    (MINOR, ["license"]),
]
APP_LAYOUT = [
    (MAJOR, ["install", "home_assistant"]),
    (MAJOR, ["version", "image_pulls"]),
    (MINOR, ["stage", "ingress", "architectures", "base_image", "mounts", "privileged", "apparmor"]),
    (MINOR, ["stars", "forks", "checks", "runtime_tests", "issues"]),
    (SUPPORT, ["paypal", "beer"]),
    (MINOR, ["license"]),
]
# Badges that only make sense in a project's own README, not in a catalog listing. The catalog
# names its licenses in one closing note instead of a badge per entry.
README_ONLY = {"paypal", "beer", "install", "license"}


def _links(ctx):
    return config.github_url(ctx["repo"])


def _community_links(ctx):
    """Where stars, issues and the license point.

    An app is part of the catalog: people star it, report problems and read the license there. The
    catalog's own listing links every entry to its repository instead, so only a project README
    (standalone) is redirected, and only for apps, which name their catalog in the context.
    """
    hub = ctx.get("hub")
    return config.github_url(hub) if hub and ctx.get("standalone") else _links(ctx)


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


def architectures(ctx):
    """One badge for the supported architectures and their image sizes: 'amd64 16.8 · aarch64 19.9 MiB'.

    Architectures come in canonical order. Until the pipeline has measured the images the badge
    names the architectures alone, so the information is never missing.
    """
    sizes = measured(ctx, "image_size") or {}
    declared = sorted(ctx["data"]["arch"], key=architecture_rank)
    if not any(arch in sizes for arch in declared):
        return [static("arch", " · ".join(declared), "ok")]
    last_measured = next(arch for arch in reversed(declared) if arch in sizes)
    parts = [f"{arch} {sizes[arch].removesuffix(' MiB')}" if arch in sizes else arch for arch in declared]
    parts[declared.index(last_measured)] += " MiB"
    message = " · ".join(parts)
    return [static("arch & size", message, "ok")]


def when(condition, badges):
    return badges if condition else []


def version(ctx, label="version", stage_only=False):
    """Declared app snapshots or the newest integration release, with metadata fallback.

    With `stage_only` a pre-release shows its stage alone ("Alpha 10"): the numbers in front of
    it never change while the stage counts up.
    """
    tag = latest_tag(ctx) or ""
    declared = str(ctx["data"]["version"])
    if ctx.get('declared_app_version'):
        # A catalog installs this config, including intentional version resets.
        # Never label it with a different historical release from the same repository.
        if tag.removeprefix('v') != declared:
            tag = ''
        shown = declared
    else:
        shown = tag.removeprefix("v") if tag else declared
    if stage_only and is_prerelease(shown):
        shown = release_title(shown)
    return [static(label, shown, "info", f"{_links(ctx)}/releases/tag/{tag}" if tag else f"{_links(ctx)}/releases")]


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
        "beer": lambda c: [support_badge("beer")],
        "home_assistant": home_assistant,
        "stars": lambda c: when(has(c, "stars"),
                                [github("stars", c["repo"], "stars", f"{_community_links(c)}/stargazers")]),
        "forks": lambda c: when(has(c, "forks"),
                                [github("forks", c["repo"], "forks", f"{_community_links(c)}/forks")]),
        "issues": lambda c: [github("issues", c["repo"], "issues", f"{_community_links(c)}/issues")],
        "checks": lambda c: when(has(c, "builds"), [workflow(
            c["repo"], "ci.yml", "checks", f"{_links(c)}/actions/workflows/ci.yml", branch=c.get("branch"))]),
        "license": lambda c: when(has_license(c), [github("license", c["repo"], "license", f"{_community_links(c)}#license")]),
    }


def _app_builders():
    def flag(label, value, color, condition):
        return lambda c: [static(label, value(c["data"]), color)] if condition(c["data"]) else []

    builders = _common_builders()
    builders.update({
        "install": lambda c: [install_badge()],
        "version": lambda c: version({**c, "declared_app_version": True}, "app version", stage_only=True),
        "image_pulls": lambda c: measurement(c, "image_pulls", "image pulls", "info"),
        "runtime_tests": lambda c: measurement(c, "runtime_tests", "runtime tests", "stable", " passed"),
        "architectures": architectures,
        "base_image": lambda c: [static("base image", c["base_image"], "info",
                                         "https://github.com/seb5594/home-assistant-base-multi-arch")]
        if c["base_image"] else [],
        "mounts": lambda c: mount_badges(c["data"]),
        "stage": lambda c: [static("stage", c["data"].get("stage", "stable"), "stable")],
        "ingress": flag("ingress", lambda d: "enabled", "accent", lambda d: d.get("ingress")),
        "privileged": flag("privileged", lambda d: ", ".join(d["privileged"]), "write",
                           lambda d: d.get("privileged")),
        "apparmor": flag("apparmor", lambda d: "disabled", "write", lambda d: d.get("apparmor") is False),
    })
    return builders


def _integration_builders():
    builders = _common_builders()
    builders.update({
        "install": lambda c: [hacs_badge(c["repo"])],
        "version": lambda c: version(c, "integration version"),
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


def app_rows(data, repo, standalone=True, live=None, measured_values=None, licensed=False, branch=None, base_image=None):
    context = {"data": data, "repo": repo, "live": live, "metrics": measured_values, "licensed": licensed,
               "minimum": data.get("homeassistant"), "hub": config.APPS_CATALOG, "standalone": standalone, "branch":branch, "base_image": base_image}
    return build_rows(APP_LAYOUT, _app_builders(), context, standalone)


def integration_rows(manifest, hacs, repo, standalone=True, live=None, measured_values=None, compat=False,
                     licensed=False):
    """`compat` marks projects that keep the Compatibility workflow (tests against real releases)."""
    context = {"data": manifest, "repo": repo, "live": live, "metrics": measured_values, "compat": compat,
               "licensed": licensed, "minimum": hacs.get("homeassistant")}
    return build_rows(INTEGRATION_LAYOUT, _integration_builders(), context, standalone)
