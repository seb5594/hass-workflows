#!/usr/bin/env python3
"""Discover seb5594's public apps or integrations and render the catalog.

Runs inside a checkout of the catalog repository (the working directory, or CATALOG_ROOT).
CATALOG_KIND selects `apps` (default) or `integrations`; static text and metadata come from
.templates/catalog/<kind> of this engine. Apps are pinned as Git submodules because the Supervisor
installs from the repository tree; integrations are only described, so nothing is cloned. Both
record their pins in .github/catalog.json for the hub. Private, archived and disabled repositories
are never listed or pinned, so a public catalog does not reveal that they exist.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

import badgekit
import config
import excerpt
import github_api
import licenses
import live
import metrics
import remote
import templating

ENGINE = config.ENGINE_ROOT
KIND = os.environ.get("CATALOG_KIND", "apps")
TEMPLATES = ENGINE / ".templates/catalog" / KIND
ROOT = Path(os.environ.get("CATALOG_ROOT", ".")).resolve()
OWNER = config.OWNER
CATALOG_REPOSITORY = config.CATALOGS[KIND]
EXCLUDED_REPOSITORIES = set()
EXCERPT_MAX_CHARS = 500
NAME_PATTERNS = {
    "apps": r"^Home-Assistant-(?P<project>[A-Za-z0-9][A-Za-z0-9._-]*)-(?:Apps?|Addon)$",
    "integrations": r"^(?i:hass|Home-Assistant)-(?P<project>[A-Za-z0-9][A-Za-z0-9._-]*)-(?i:integration)$",
}
NAME_PATTERN = re.compile(NAME_PATTERNS[KIND])
CONFIG_NAMES = {"config.yaml", "config.yml", "config.json"}


def git(*args, cwd=None):
    """Run Git without a shell and never swallow errors."""
    return subprocess.run(
        ["git", *args], cwd=cwd or ROOT, check=True, text=True, stdout=subprocess.PIPE,
        timeout=180, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    ).stdout.strip()


def discover_repositories(excluded):
    """Walk every API page instead of relying on search indexing."""
    repositories, page = [], 1
    while True:
        batch = github_api.fetch_json(f"https://api.github.com/users/{OWNER}/repos"
                                      f"?type=owner&sort=full_name&per_page=100&page={page}")
        if not isinstance(batch, list):
            raise ValueError("Expected a repository list from GitHub.")
        repositories.extend(
            repo for repo in batch
            if repo["owner"]["login"].casefold() == OWNER.casefold()
            and NAME_PATTERN.fullmatch(repo["name"])
            and not (repo.get("private") or repo.get("archived") or repo.get("disabled"))
            and repo["name"] not in excluded)
        if len(batch) < 100:
            break
        page += 1
    return sorted(repositories, key=lambda repo: repo["name"].casefold())


def readme_excerpt(folder, fallback, limit):
    """First prose paragraph of the README, without headings, badges or code."""
    readme = next((p for p in sorted(folder.iterdir())
                   if p.is_file() and p.name.casefold() == "readme.md"), None)
    return excerpt.first_paragraph(readme.read_text(encoding="utf-8") if readme else "", limit, fallback)


def app_metadata(folder):
    """Check the catalog fields; Supervisor still validates the complete app schema."""
    apps = []
    for config_file in sorted(folder.rglob("config.*")):
        parts = config_file.relative_to(folder).parts
        if config_file.name not in CONFIG_NAMES or any(p.startswith(".") or p == "rootfs" for p in parts):
            continue
        if config_file.is_symlink():
            raise ValueError(f"App configurations must not be symlinks: {config_file}")
        data = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "slug" not in data:
            continue
        for key in ("name", "version", "slug", "description"):
            if not isinstance(data.get(key), str) or not data[key].strip():
                raise ValueError(f"Missing or invalid {key!r} in {config_file}")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", data["slug"]):
            raise ValueError(f"Invalid app slug in {config_file}")
        if not isinstance(data.get("arch"), list) or not data["arch"] or not set(data["arch"]) <= set(config.PLATFORMS):
            raise ValueError(f"Invalid architectures in {config_file}")
        apps.append({**data, "path": config_file.parent.relative_to(folder).as_posix(),
                     "excerpt": readme_excerpt(config_file.parent, data["description"], EXCERPT_MAX_CHARS)})
    if not apps:
        raise ValueError(f"No Home Assistant app configuration found in {folder.name}.")
    return apps


def current_submodules():
    """Read paths and URLs from .gitmodules without assuming submodule names."""
    if not (ROOT / ".gitmodules").exists():
        return {}
    result = {}
    for line in git("config", "--file", ".gitmodules", "--list").splitlines():
        key, value = line.split("=", 1)
        if key.startswith("submodule.") and key.endswith(".path"):
            prefix = key.removesuffix(".path")
            result[value] = {"key": prefix, "url": git("config", "--file", ".gitmodules", f"{prefix}.url")}
    return result


def project_path(name):
    """Strip the naming prefix and suffix without changing the project's case."""
    if not (match := NAME_PATTERN.fullmatch(name)):
        raise ValueError(f"Invalid source repository name: {name}")
    return match["project"]


def managed_submodules(modules):
    """Our generated folders are the submodules that point at matching seb5594 repositories."""
    managed, prefix = {}, f"https://github.com/{OWNER}/"
    for path, module in modules.items():
        url = module["url"]
        if not url.startswith(prefix) or not url.endswith(".git"):
            continue
        name = url[len(prefix):-4]
        if NAME_PATTERN.fullmatch(name) and path in {name, project_path(name)}:
            managed[path] = {**module, "repository_name": name}
    return managed


def sync_repository(repo, modules, limit):
    """Pin exactly the latest commit of the repository's default branch."""
    name, branch = repo["name"], repo["default_branch"]
    path = project_path(name)
    folder = ROOT / path
    url = f"{config.github_url(OWNER + '/' + name)}.git"
    existing = [old for old, module in managed_submodules(modules).items() if module["url"] == url]
    if len(existing) > 1:
        raise ValueError(f"Multiple managed submodules reference {name}.")
    if existing and existing[0] != path:
        if folder.exists() or path in modules:
            raise ValueError(f"Refusing to overwrite an existing directory: {path}")
        git("submodule", "update", "--init", "--", existing[0])
        git("mv", "--", existing[0], path)
        modules = current_submodules()
    if path not in modules:
        if folder.exists():
            raise ValueError(f"Refusing to overwrite an unmanaged directory: {path}")
        git("submodule", "add", "--", url, path)
    else:
        if modules[path]["url"] != url:
            raise ValueError(f"Unexpected submodule URL for {name}; fix .gitmodules first.")
        git("submodule", "sync", "--", path)
        git("submodule", "update", "--init", "--", path)
    git("fetch", "--depth=1", "origin", f"refs/heads/{branch}", cwd=folder)
    sha = git("rev-parse", "FETCH_HEAD", cwd=folder)
    git("checkout", "--detach", sha, cwd=folder)
    git("submodule", "update", "--init", "--recursive", cwd=folder)
    items = app_metadata(folder)
    return {"repository": f"{OWNER}/{name}", "path": path, "branch": branch, "commit": sha,
            "url": config.github_url(f"{OWNER}/{name}"), "live": live.fetch(f"{OWNER}/{name}"),
            "excerpt": readme_excerpt(folder, repo.get("description") or items[0]["description"], limit),
            "metrics": metrics.load(folder), "items": items}


def describe_repository(repo, limit):
    """Integrations are read remotely at the current head commit; nothing is cloned or pinned."""
    name, repository = repo["name"], f"{OWNER}/{repo['name']}"
    sha = remote.head_commit(repository, repo["default_branch"])
    items, summary = remote.describe(repository, sha, KIND, limit, repo.get("description") or "")
    if not items:
        raise ValueError(f"No Home Assistant integration found in {name}.")
    return {"repository": repository, "path": project_path(name), "branch": repo["default_branch"],
            "commit": sha, "url": config.github_url(repository), "live": live.fetch(repository),
            "excerpt": summary, "items": items}


def render_header(entries, own=None):
    """Header badges; `own` holds live facts about the catalog repository (None keeps everything)."""
    items = [item for entry in entries for item in entry["items"]]
    link = config.github_url(CATALOG_REPOSITORY)
    context = {"repo": CATALOG_REPOSITORY, "data": {}, "forks": 0, "live": own}
    status = badgekit.when(badgekit.has(context, "builds"), [badgekit.workflow(
        CATALOG_REPOSITORY, "update.yml", "catalog sync", f"{link}/actions/workflows/update.yml")])
    status.append(badgekit.static(KIND, str(len(items)), "info"))
    stats = badgekit.when(badgekit.has(context, "stars"),
                          [badgekit.github("stars", CATALOG_REPOSITORY, "stars", f"{link}/stargazers")])
    stats += badgekit.when(own is not None and badgekit.has(context, "forks"),
                           [badgekit.github("forks", CATALOG_REPOSITORY, "forks", f"{link}/forks")])
    stats.append(badgekit.github("last-commit", CATALOG_REPOSITORY, "synced", f"{link}/commits/main"))
    return badgekit.render([
        [badgekit.install_badge()] if KIND == "apps" else [],
        status,
        stats,
    ])


def item_rows(item, entry):
    """Badge lists of one listed project; README-only badges and the row sizes are left out."""
    if KIND == "integrations":
        rows = badgekit.integration_rows(item, item["hacs"], entry["repository"], standalone=False,
                                         live=entry.get("live"), measured_values=item.get("metrics"),
                                         compat=item.get("compat", False))
    else:
        rows = badgekit.app_rows(item, entry["repository"], standalone=False, live=entry.get("live"),
                                 measured_values=entry.get("metrics"))
    return badgekit.plain(rows)


def entry_heading(entry):
    """Project name with the version currently on the default branch in parentheses."""
    items = entry["items"]
    version = (str(items[0]["version"]) if len(items) == 1
               else ", ".join(f"{item['slug']} {item['version']}" for item in items))
    return f"### [{entry['path']}]({entry['url']}) ({version})"


def changelog_link(entry, item):
    folder = "" if KIND == "integrations" else f"{item['path']}/"
    return f"[Changelog]({entry['url']}/blob/{entry.get('branch', 'main')}/{folder}CHANGELOG.md)"


def render_item(entry, item):
    """The changelog link starts the badge paragraph; several items per repository keep their names."""
    label = changelog_link(entry, item)
    if len(entry["items"]) > 1:
        label = f"**{item['name']}** · {label}"
    return f"{label}<br>\n{badgekit.render(item_rows(item, entry))}"


def render_catalog(entries):
    sections = []
    for entry in entries:
        if KIND == "apps" and len(entry["items"]) > 1:
            # One pinned source submodule; a separate documented entry per installable app.
            for item in entry["items"]:
                folder = item['path'].strip('/')
                source = f"{entry['url']}/tree/{entry['commit']}" + (f"/{folder}" if folder else "")
                sections += [f"### [{item['name']}]({source}) ({item['version']})", "",
                             f"> {item.get('excerpt') or item['description']}", "",
                             render_item(entry, item), "",
                             f"[README & setup]({source}) · "
                             f"[Pinned commit `{entry['commit'][:7]}`]({entry['url']}/commit/{entry['commit']})", ""]
            continue
        sections += [entry_heading(entry), "", f"> {entry['excerpt']}", ""]
        for item in entry["items"]:
            sections += [render_item(entry, item), ""]
        sections += [f"[Source & documentation]({entry['url']}) · "
                     f"[Pinned commit `{entry['commit'][:7]}`]({entry['url']}/commit/{entry['commit']})", ""]
    return "\n".join(sections).strip() or f"No matching {KIND} are currently available."


def license_note(entries):
    """Appears only once at least one listed project has a license."""
    licensed = any((entry.get("live") or {}).get("license") for entry in entries)
    return licenses.COLLECTION_NOTE if licensed else ""


def render_readme(entries, own=None):
    template = (TEMPLATES / "README.md").read_text(encoding="utf-8")
    text = templating.fill(template, {
        "BADGES": render_header(entries, own), "APP_CATALOG": render_catalog(entries),
        "SUPPORT": badgekit.support_section(), "LICENSE_NOTE": license_note(entries)})
    return text.rstrip("\n") + "\n"


def repository_yaml():
    metadata = json.loads((TEMPLATES / "repository.json").read_text(encoding="utf-8"))
    if not isinstance(metadata, dict) or set(metadata) - {"name", "url", "maintainer"}:
        raise ValueError("Repository template must contain only name, url and maintainer.")
    if any(not isinstance(value, str) or not value.strip() for value in metadata.values()) or "name" not in metadata:
        raise ValueError("Repository metadata needs a nonempty name and nonempty string values.")
    return yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True)


def write_listing(entries):
    """Pins for the hub, kept out of the repository root."""
    listing = [{"repository": entry["repository"], "commit": entry["commit"]} for entry in entries]
    target = ROOT / ".github/catalog.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(listing, indent=2) + "\n", encoding="utf-8")


def main():
    metadata = repository_yaml() if KIND == "apps" else None
    repositories = discover_repositories(EXCLUDED_REPOSITORIES)
    modules = current_submodules()
    if managed_submodules(modules) and not repositories:
        raise ValueError("Refusing to remove the whole catalog; check the API and exclusions.")
    paths = [project_path(repo["name"]).casefold() for repo in repositories]
    if len(paths) != len(set(paths)):
        raise ValueError("Multiple source repositories resolve to the same folder.")
    if KIND == "apps":
        entries = [sync_repository(repo, modules, EXCERPT_MAX_CHARS) for repo in repositories]
    else:
        entries = [describe_repository(repo, EXCERPT_MAX_CHARS) for repo in repositories]
    slugs = [item["slug"] for entry in entries for item in entry["items"]]
    if len(slugs) != len(set(slugs)):
        raise ValueError("Duplicate slugs would collide in Home Assistant.")
    # Submodules left over from earlier runs go only after every current source validated.
    wanted = {entry["path"] for entry in entries} if KIND == "apps" else set()
    for path in managed_submodules(current_submodules()):
        if path not in wanted:
            git("rm", "--force", "--", path)
    gitmodules = ROOT / ".gitmodules"
    if gitmodules.exists() and not gitmodules.read_text().strip():
        gitmodules.unlink()
    own = live.fetch_own(CATALOG_REPOSITORY, "update.yml")
    (ROOT / "README.md").write_text(render_readme(entries, own), encoding="utf-8")
    if metadata:
        (ROOT / "repository.yaml").write_text(metadata, encoding="utf-8")
    write_listing(entries)
    print(f"Synchronized {len(entries)} repositories and {len(slugs)} {KIND}.")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write(f"## Catalog\n\n{render_catalog(entries)}\n")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError, yaml.YAMLError) as error:
        print(f"Synchronization failed: {error}", file=sys.stderr)
        sys.exit(1)
