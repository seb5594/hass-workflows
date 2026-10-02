#!/usr/bin/env python3
"""Render the Home Assistant Hub README from the app and integration catalogs.

The hub reads each catalog's `.gitmodules` and pinned commits, then the metadata of every listed
project at exactly that commit, so it always agrees with what the catalogs show. Run inside a
checkout of the hub repository (the working directory, or HUB_ROOT).
"""
import json
import os
import re
import sys
from pathlib import Path

import yaml

import badgekit
import github_api

ENGINE = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("HUB_ROOT", ".")).resolve()
OWNER = "seb5594"
HUB_REPOSITORY = f"{OWNER}/Home-Assistant-Hub"
CATALOGS = {"apps": f"{OWNER}/Home-Assistant-Apps", "integrations": f"{OWNER}/Home-Assistant-Integrations"}
RAW = "https://raw.githubusercontent.com"
API = "https://api.github.com"


def fetch_json(url):
    return github_api.fetch_json(url, f"{OWNER}-hub")


def fetch_text(url):
    return github_api.fetch_text(url, f"{OWNER}-hub")


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
    """(source repository, pinned commit) for every submodule of a catalog."""
    try:
        modules = fetch_text(f"{RAW}/{catalog}/main/.gitmodules")
    except RuntimeError:
        return []
    projects = []
    for path, repository in parse_modules(modules):
        pinned = fetch_json(f"{API}/repos/{catalog}/contents/{path}")
        projects.append((repository, pinned["sha"]))
    return projects


def project_files(repository, sha):
    tree = fetch_json(f"{API}/repos/{repository}/git/trees/{sha}?recursive=1")
    return [entry["path"] for entry in tree["tree"] if entry["type"] == "blob"]


def raw(repository, sha, path):
    return fetch_text(f"{RAW}/{repository}/{sha}/{path}")


def load_apps(repository, files, sha):
    apps = []
    for path in sorted(files):
        parts = path.split("/")
        if parts[-1] not in {"config.yaml", "config.yml"} or any(p.startswith(".") for p in parts):
            continue
        data = yaml.safe_load(raw(repository, sha, path))
        if isinstance(data, dict) and "slug" in data:
            apps.append(data)
    return apps


def load_integrations(repository, files, sha):
    hacs = json.loads(raw(repository, sha, "hacs.json")) if "hacs.json" in files else {}
    manifests = [p for p in sorted(files) if re.fullmatch(r"custom_components/[^/]+/manifest\.json", p)]
    return [{**json.loads(raw(repository, sha, path)), "hacs": hacs} for path in manifests]


def collect(kind):
    entries = []
    loader = load_apps if kind == "apps" else load_integrations
    for repository, sha in listed_projects(CATALOGS[kind]):
        files = project_files(repository, sha)
        items = loader(repository, files, sha)
        if items:
            entries.append({"repository": repository, "sha": sha, "items": items})
    return entries


def cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def title_cell(name, link, description):
    """Linked name, with the description on a second line only when there is one."""
    text = f"**[{cell(name)}]({link})**"
    return f"{text}<br>{cell(description)}" if description else text


def project_link(entry):
    return f"https://github.com/{entry['repository']}"


def app_table(entries):
    rows = ["| App | Version | Architectures | Status |", "| --- | --- | --- | --- |"]
    for entry in entries:
        link, repo = project_link(entry), entry["repository"]
        for app in entry["items"]:
            status = " ".join([badgekit.workflow(repo, "ci.yml", "build", f"{link}/actions/workflows/ci.yml"),
                               badgekit.github("stars", repo, "stars", f"{link}/stargazers")])
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
            status = " ".join([badgekit.workflow(repo, "ci.yml", "checks", f"{link}/actions/workflows/ci.yml"),
                               badgekit.github("downloads", repo, "downloads", f"{link}/releases", "/total")])
            rows.append(f"| {title_cell(manifest['name'], link, manifest.get('description'))} "
                        f"| {badgekit.static('version', manifest['version'], 'info', f'{link}/releases')} "
                        f"| {'≥ ' + minimum if minimum else '–'} | {status} |")
    return "\n".join(rows)


def render_header(apps, integrations):
    hub = f"https://github.com/{HUB_REPOSITORY}"
    projects = len(apps) + len(integrations)
    return badgekit.render([
        badgekit.install_row()[:1]
        + [badgekit.static("HACS", "browse integrations", "info", f"https://github.com/{CATALOGS['integrations']}")],
        [badgekit.workflow(HUB_REPOSITORY, "update.yml", "hub sync", f"{hub}/actions/workflows/update.yml"),
         badgekit.static("apps", str(sum(len(e["items"]) for e in apps)), "ok", f"https://github.com/{CATALOGS['apps']}"),
         badgekit.static("integrations", str(sum(len(e["items"]) for e in integrations)), "ok",
                         f"https://github.com/{CATALOGS['integrations']}"),
         badgekit.static("repositories", str(projects), "muted")],
        [badgekit.github("stars", HUB_REPOSITORY, "stars", f"{hub}/stargazers"),
         badgekit.github("last-commit", HUB_REPOSITORY, "synced", f"{hub}/commits/main")],
        badgekit.support_badges(),
    ])


def render_readme(apps, integrations):
    template = (ENGINE / ".templates/hub/README.md").read_text(encoding="utf-8")
    for placeholder in ("{{BADGES}}", "{{APPS}}", "{{INTEGRATIONS}}"):
        if template.count(placeholder) != 1:
            raise ValueError(f"README template must contain exactly one {placeholder} placeholder.")
    return (template.replace("{{BADGES}}", render_header(apps, integrations))
            .replace("{{APPS}}", app_table(apps) if apps else "_No apps are published yet._")
            .replace("{{INTEGRATIONS}}", integration_table(integrations) if integrations
                     else "_No integrations are published yet._"))


def main():
    apps, integrations = collect("apps"), collect("integrations")
    if not apps and not integrations:
        raise ValueError("Both catalogs came back empty; refusing to overwrite the hub README.")
    (ROOT / "README.md").write_text(render_readme(apps, integrations), encoding="utf-8")
    print(f"Hub lists {sum(len(e['items']) for e in apps)} apps and "
          f"{sum(len(e['items']) for e in integrations)} integrations.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, yaml.YAMLError) as error:
        print(f"Hub update failed: {error}", file=sys.stderr)
        sys.exit(1)
