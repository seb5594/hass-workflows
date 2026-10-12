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


def title_cell(name, link, description):
    """Linked name, with the description on a second line only when there is one."""
    text = f"**[{cell(name)}]({link})**"
    return f"{text}<br>{cell(description)}" if description else text


def project_link(entry):
    return config.github_url(entry["repository"])


def app_table(entries):
    rows = ["| App | Version | Architectures | Status |", "| --- | --- | --- | --- |"]
    for entry in entries:
        link, repo = project_link(entry), entry["repository"]
        for app in entry["items"]:
            facts = {"repo": repo, "live": entry.get("live")}
            status = " ".join(
                badgekit.when(badgekit.has(facts, "builds"), [badgekit.workflow(
                    repo, "ci.yml", "build", f"{link}/actions/workflows/ci.yml")])
                + badgekit.when(badgekit.has(facts, "stars"), [badgekit.github(
                    "stars", repo, "stars", f"{link}/stargazers")]))
            rows.append(f"| {title_cell(app['name'], link, app.get('description'))} "
                        f"| {badgekit.static('version', app['version'], 'info', f'{link}/releases')} "
                        f"| {' · '.join(app['arch'])} | {status} |")
    return "\n".join(rows)


def integration_table(entries):
    rows = ["| Integration | Version | Home Assistant | Status |", "| --- | --- | --- | --- |"]
    for entry in entries:
        link, repo = project_link(entry), entry["repository"]
        for manifest in entry["items"]:
            minimum = manifest["hacs"].get("homeassistant")
            facts = {"repo": repo, "live": entry.get("live")}
            status = " ".join(
                badgekit.when(badgekit.has(facts, "builds"), [badgekit.workflow(
                    repo, "ci.yml", "checks", f"{link}/actions/workflows/ci.yml")])
                + badgekit.when(badgekit.has(facts, "releases"), [badgekit.github(
                    "downloads", repo, "downloads", f"{link}/releases", "/total", "info")]))
            rows.append(f"| {title_cell(manifest['name'], link, manifest.get('description'))} "
                        f"| {badgekit.static('version', manifest['version'], 'info', f'{link}/releases')} "
                        f"| {'≥ ' + minimum if minimum else '–'} | {status} |")
    return "\n".join(rows)


def render_header(apps, integrations, own=None):
    hub = config.github_url(HUB_REPOSITORY)
    projects = len(apps) + len(integrations)
    context = {"live": own}
    return badgekit.render([
        [badgekit.install_badge()]
        + [badgekit.static("HACS", "browse integrations", "info", config.github_url(CATALOGS["integrations"]))],
        badgekit.when(badgekit.has(context, "builds"), [badgekit.workflow(
            HUB_REPOSITORY, "update.yml", "hub sync", f"{hub}/actions/workflows/update.yml")])
        + [badgekit.static("apps", str(sum(len(e["items"]) for e in apps)), "ok", config.github_url(CATALOGS["apps"])),
           badgekit.static("integrations", str(sum(len(e["items"]) for e in integrations)), "ok",
                           config.github_url(CATALOGS["integrations"])),
           badgekit.static("repositories", str(projects), "muted")],
        badgekit.when(badgekit.has(context, "stars"), [badgekit.github(
            "stars", HUB_REPOSITORY, "stars", f"{hub}/stargazers")])
        + [badgekit.github("last-commit", HUB_REPOSITORY, "synced", f"{hub}/commits/main")],
    ])


def render_readme(apps, integrations, own=None):
    text = templating.fill((ENGINE / ".templates/hub/README.md").read_text(encoding="utf-8"), {
        "BADGES": render_header(apps, integrations, own), "SUPPORT": badgekit.support_section(),
        "LICENSE_NOTE": licenses.COLLECTION_NOTE,
        "APPS": app_table(apps) if apps else "_No apps are published yet._",
        "INTEGRATIONS": (integration_table(integrations) if integrations
                         else "_No integrations are published yet._")})
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
