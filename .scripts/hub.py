#!/usr/bin/env python3
"""Render the Home Assistant Hub README from the app and integration catalogs.

The hub reads which projects each catalog lists and the commit it pins (`.github/catalog.json`),
then the metadata of every project at exactly that commit, so it always agrees with the catalogs.
Run inside a checkout of the hub repository (the working directory, or HUB_ROOT).
"""
import json
import os
import re
import sys
from pathlib import Path

import yaml

import badgekit
import config
import licenses
import live
import remote
import templating

ENGINE = config.ENGINE_ROOT
ROOT = Path(os.environ.get("HUB_ROOT", ".")).resolve()
HUB_REPOSITORY = config.HUB_REPOSITORY
CATALOGS = config.CATALOGS


def parse_modules(text):
    """(path, owner/name) for every submodule; comments and key order do not matter."""
    modules, current = [], {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("[submodule"):
            current = {}
            modules.append(current)
        elif "=" in line and not line.startswith(("#", ";")):
            key, value = (part.strip() for part in line.split("=", 1))
            current[key] = value
    found = []
    for module in modules:
        match = re.fullmatch(r"https://github\.com/([^/]+/[^/]+?)(?:\.git)?", module.get("url", ""))
        if match and "path" in module:
            found.append((module["path"], match.group(1)))
    return found


def listed_projects(catalog):
    """(source repository, pinned commit) for everything a catalog lists."""
    try:
        listing = json.loads(remote.fetch_text(f"{remote.RAW}/{catalog}/main/.github/catalog.json"))
        return [(entry["repository"], entry["commit"]) for entry in listing]
    except RuntimeError:
        pass
    # Catalogs created before catalog.json existed only record their pins as submodules.
    try:
        modules = remote.fetch_text(f"{remote.RAW}/{catalog}/main/.gitmodules")
    except RuntimeError:
        return []
    return [(repository, remote.fetch_json(f"{remote.API}/repos/{catalog}/contents/{path}")["sha"])
            for path, repository in parse_modules(modules)]


def collect(kind):
    entries = []
    for repository, sha in listed_projects(CATALOGS[kind]):
        items, _ = remote.describe(repository, sha, kind, 160)
        if items:
            entries.append({"repository": repository, "sha": sha, "items": items,
                            "live": live.fetch(repository)})
    return entries


def cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


ICON_HEIGHT = 64
LOGO_URL = f"{remote.RAW}/{CATALOGS['integrations']}/main/assets/seb5594.png"
TAGLINE = "Everything I publish for Home Assistant, in one place."


def title_cell(name, link, description):
    """Linked name, with the description on a second line only when it adds something."""
    text = f"**[{cell(name)}]({link})**"
    if not description or cell(description).casefold() == cell(name).casefold():
        return text
    return f"{text}<br>{cell(description)}"


def project_link(entry):
    return config.github_url(entry["repository"])


def icon_cell(entry, item):
    """The project's own icon at the pinned commit, or an empty cell."""
    if not item.get("icon"):
        return ""
    url = f"{remote.RAW}/{entry['repository']}/{entry['sha']}/{item['icon']}"
    return f'<img src="{url}" height="{ICON_HEIGHT}" alt="">'


def status_badges(entry, workflow_label, extra):
    facts = {"repo": entry["repository"], "live": entry.get("live")}
    link = project_link(entry)
    return badgekit.render([
        badgekit.when(badgekit.has(facts, "builds"), [badgekit.workflow(
            entry["repository"], "ci.yml", workflow_label, f"{link}/actions/workflows/ci.yml")])
        + badgekit.when(badgekit.has(facts, extra[0]), [extra[1]])])


def total_line(label, total, count, unit):
    """One sentence under a table: the summed counter and how many projects it comes from."""
    return f"**{label}:** {total:,} across {count} {unit}." if total else ""


def app_pulls(entries):
    """Sum of the measured image pulls of every listed app."""
    return sum(int((app.get("metrics") or {}).get("image_pulls") or 0)
               for entry in entries for app in entry["items"])


def integration_downloads(entries):
    """Sum of the release downloads of every listed integration repository."""
    return sum(int((entry.get("live") or {}).get("downloads") or 0) for entry in entries)


def app_table(entries):
    rows = ["| | App | Version | Runs on | Status |", "| :---: | --- | --- | --- | --- |"]
    for entry in entries:
        link, repo = project_link(entry), entry["repository"]
        for app in entry["items"]:
            status = " ".join(filter(None, (
                badgekit.render([badgekit.measurement({"metrics": app.get("metrics")}, "image_pulls", "pulls", "info")]),
                status_badges(entry, "build", ("stars", badgekit.github("stars", repo, "stars", f"{link}/stargazers"))))))
            rows.append(f"| {icon_cell(entry, app)} | {title_cell(app['name'], link, app.get('description'))} "
                        f"| {badgekit.static('version', app['version'], 'info', f'{link}/releases')} "
                        f"| {' · '.join(app['arch'])} | {status} |")
    return "\n".join(rows)


def integration_table(entries):
    rows = ["| | Integration | Version | Home Assistant | Status | |", "| :---: | --- | --- | --- | --- | :---: |"]
    for entry in entries:
        link, repo = project_link(entry), entry["repository"]
        for manifest in entry["items"]:
            minimum = manifest["hacs"].get("homeassistant")
            status = status_badges(entry, "checks", ("releases", badgekit.github(
                "downloads", repo, "downloads", f"{link}/releases", "/total", "info")))
            install = badgekit.hacs_badge(repo)
            rows.append(f"| {icon_cell(entry, manifest)} | {title_cell(manifest['name'], link, manifest.get('description'))} "
                        f"| {badgekit.static('version', manifest['version'], 'info', f'{link}/releases')} "
                        f"| {'≥ ' + minimum if minimum else '–'} | {status} | [Install]({install.link}) |")
    return "\n".join(rows)


def render_header(apps, integrations, own=None):
    """Logo and title in one centered heading, then the badges in three sized rows and a navigation."""
    hub = config.github_url(HUB_REPOSITORY)
    context = {"live": own}
    rows = [
        badgekit.Row(badgekit.MAJOR, [badgekit.install_badge(), badgekit.static(
            "HACS", "browse integrations", "info", config.github_url(CATALOGS["integrations"]))]),
        badgekit.Row(badgekit.MAJOR, [
            badgekit.static("apps", str(sum(len(e["items"]) for e in apps)), "ok", config.github_url(CATALOGS["apps"])),
            badgekit.static("integrations", str(sum(len(e["items"]) for e in integrations)), "ok",
                            config.github_url(CATALOGS["integrations"]))]),
        badgekit.Row(badgekit.MINOR,
                     badgekit.when(badgekit.has(context, "stars"), [badgekit.github(
                         "stars", HUB_REPOSITORY, "stars", f"{hub}/stargazers")])
                     + badgekit.when(badgekit.has(context, "builds"), [badgekit.workflow(
                         HUB_REPOSITORY, "update.yml", "hub sync", f"{hub}/actions/workflows/update.yml")])
                     + [badgekit.github("last-commit", HUB_REPOSITORY, "synced", f"{hub}/commits/main")]),
    ]
    title = (f'<h1 align="center">\n  <img src="{LOGO_URL}" width="160" alt="">\n  <br>\n'
             f"  Home Assistant Hub\n</h1>")
    navigation = ('<p align="center">\n  <a href="#get-started">Get started</a> · <a href="#apps">Apps</a> · '
                  '<a href="#integrations">Integrations</a> · <a href="#how-this-works">How this works</a>\n</p>')
    return "\n\n".join((title, f'<p align="center"><b>{TAGLINE}</b></p>', badgekit.render_header(rows), navigation))


def render_readme(apps, integrations, own=None):
    text = templating.fill((ENGINE / ".templates/hub/README.md").read_text(encoding="utf-8"), {
        "HEADER": render_header(apps, integrations, own), "SUPPORT": badgekit.support_section(),
        "LICENSE_NOTE": licenses.COLLECTION_NOTE,
        "APPS": (app_table(apps) + "\n\n" + total_line("Total image pulls", app_pulls(apps),
                                                        sum(len(e["items"]) for e in apps), "apps")
                 if apps else "_No apps are published yet._").rstrip(),
        "INTEGRATIONS": ((integration_table(integrations) + "\n\n" + total_line(
            "Total downloads", integration_downloads(integrations), len(integrations), "integrations")).rstrip()
                         if integrations else "_No integrations are published yet._")})
    return text.rstrip("\n") + "\n"


def main():
    apps, integrations = collect("apps"), collect("integrations")
    if not apps and not integrations:
        raise ValueError("Both catalogs came back empty; refusing to overwrite the hub README.")
    own = live.fetch_own(HUB_REPOSITORY, "update.yml", os.environ.get("OWN_TOKEN"))
    (ROOT / "README.md").write_text(render_readme(apps, integrations, own), encoding="utf-8")
    print(f"Hub lists {sum(len(e['items']) for e in apps)} apps and "
          f"{sum(len(e['items']) for e in integrations)} integrations.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, yaml.YAMLError) as error:
        print(f"Hub update failed: {error}", file=sys.stderr)
        sys.exit(1)
