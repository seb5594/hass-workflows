"""Read project metadata straight from GitHub at an exact commit, without cloning."""
import json
import re

import yaml

import excerpt
import github_api

RAW = "https://raw.githubusercontent.com"
API = "https://api.github.com"


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


def load_apps(repository, sha, files):
    apps = []
    for path in sorted(files):
        parts = path.split("/")
        if parts[-1] not in {"config.yaml", "config.yml"} or any(p.startswith(".") for p in parts):
            continue
        data = yaml.safe_load(raw(repository, sha, path))
        if isinstance(data, dict) and "slug" in data:
            apps.append({**data, "path": "/".join(parts[:-1])})
    return apps


def load_integrations(repository, sha, files):
    hacs = json.loads(raw(repository, sha, "hacs.json")) if "hacs.json" in files else {}
    manifests = [p for p in sorted(files) if re.fullmatch(r"custom_components/[^/]+/manifest\.json", p)]
    items = []
    for path in manifests:
        manifest = json.loads(raw(repository, sha, path))
        items.append({**manifest, "slug": manifest["domain"], "hacs": hacs, "path": path.rsplit("/", 1)[0]})
    return items


def describe(repository, sha, kind, limit=500, fallback=""):
    """(items, summary) for the project at `sha`; integrations without a description get the README intro."""
    files = project_files(repository, sha)
    if kind == "apps":
        return load_apps(repository, sha, files), ""
    items = load_integrations(repository, sha, files)
    summary = excerpt.first_paragraph(readme(repository, sha, files), limit, fallback)
    for item in items:
        item.setdefault("description", summary)
    return items, summary
