"""Read project metadata straight from GitHub at an exact commit, without cloning."""
import json
import re

import yaml

import excerpt
import github_api

RAW = "https://raw.githubusercontent.com"
API = "https://api.github.com"
METRICS_FILE = ".github/metrics.json"
COMPAT_WORKFLOW = ".github/workflows/compat.yml"


fetch_json = github_api.fetch_json
fetch_text = github_api.fetch_text


def head_commit(repository, branch):
    return fetch_json(f"{API}/repos/{repository}/commits/{branch}")["sha"]


def project_files(repository, sha):
    tree = fetch_json(f"{API}/repos/{repository}/git/trees/{sha}?recursive=1")
    return [entry["path"] for entry in tree["tree"] if entry["type"] == "blob"]


def raw(repository, sha, path):
    return fetch_text(f"{RAW}/{repository}/{sha}/{path}")


def readme(repository, sha, files):
    name = next((p for p in files if p.casefold() == "readme.md"), None)
    return raw(repository, sha, name) if name else ""


def first_file(files, *candidates):
    """The first of the candidate paths the project contains, or None."""
    return next((path for path in candidates if path in files), None)


def load_apps(repository, sha, files):
    apps = []
    measured = optional_json(repository, sha, files, METRICS_FILE)
    for path in sorted(files):
        parts = path.split("/")
        if parts[-1] not in {"config.yaml", "config.yml"} or any(p.startswith(".") for p in parts):
            continue
        data = yaml.safe_load(raw(repository, sha, path))
        if isinstance(data, dict) and "slug" in data:
            folder = "/".join(parts[:-1])
            apps.append({**data, "path": folder, "metrics": measured, "icon": first_file(files, f"{folder}/icon.png")})
    return apps


def optional_json(repository, sha, files, path):
    return json.loads(raw(repository, sha, path)) if path in files else {}


def load_integrations(repository, sha, files):
    """Manifests plus what the listings need besides them: hacs.json, measurements, compat workflow."""
    hacs = optional_json(repository, sha, files, "hacs.json")
    measured = optional_json(repository, sha, files, METRICS_FILE)
    compat = COMPAT_WORKFLOW in files
    manifests = [p for p in sorted(files) if re.fullmatch(r"custom_components/[^/]+/manifest\.json", p)]
    items = []
    for path in manifests:
        manifest = json.loads(raw(repository, sha, path))
        folder = path.rsplit("/", 1)[0]
        items.append({**manifest, "slug": manifest["domain"], "hacs": hacs, "path": folder,
                      "metrics": measured, "compat": compat,
                      "icon": first_file(files, f"{folder}/brand/icon@2x.png", f"{folder}/brand/icon.png")})
    return items


def load_dashboards(repository, sha, files):
    """The card or theme of a dashboard repository: `hacs.json` names it, `package.json` versions it.

    The item is shaped like an integration manifest (name, slug, version, description) plus its
    HACS category, so catalogs and the hub render all remotely described projects the same way.
    """
    if "hacs.json" not in files or "package.json" not in files:
        return []
    hacs = json.loads(raw(repository, sha, "hacs.json"))
    package = json.loads(raw(repository, sha, "package.json"))
    return [{**package, "name": hacs["name"], "slug": package["name"].rpartition("/")[2], "hacs": hacs,
             "category": "plugin" if hacs.get("filename") else "theme", "path": "",
             "metrics": optional_json(repository, sha, files, METRICS_FILE), "compat": False,
             "icon": first_file(files, "brand/icon@2x.png", "brand/icon.png")}]


LOADERS = {"integrations": load_integrations, "dashboards": load_dashboards}


def describe(repository, sha, kind, limit=500, fallback=""):
    """(items, summary) for the project at `sha`; projects without a description get the README intro."""
    files = project_files(repository, sha)
    if kind == "apps":
        return load_apps(repository, sha, files), ""
    items = LOADERS[kind](repository, sha, files)
    summary = excerpt.first_paragraph(readme(repository, sha, files), limit, fallback)
    for item in items:
        item.setdefault("description", summary)
    return items, summary
