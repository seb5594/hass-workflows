#!/usr/bin/env python3
"""Discover seb5594's public apps, pin them as submodules and render the catalog README.

Runs inside a checkout of the catalog repository (the working directory, or CATALOG_ROOT);
the static text and repository metadata come from .templates/catalog of this engine.
"""
import html
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

import badgekit

ENGINE = Path(__file__).resolve().parents[1]
TEMPLATES = ENGINE / ".templates/catalog"
ROOT = Path(os.environ.get("CATALOG_ROOT", ".")).resolve()
OWNER = "seb5594"
CATALOG_REPOSITORY = f"{OWNER}/Home-Assistant-Apps"
EXCLUDED_REPOSITORIES = set()
EXCERPT_MAX_CHARS = 500
NAME_PATTERN = re.compile(r"^Home-Assistant-(?P<project>[A-Za-z0-9][A-Za-z0-9._-]*)-(?:App|Addon)$")
ARCHITECTURES = {"aarch64", "amd64", "armhf", "armv7", "i386"}
CONFIG_NAMES = {"config.yaml", "config.yml", "config.json"}
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def git(*args, cwd=None):
    """Run Git without a shell and never swallow errors."""
    return subprocess.run(
        ["git", *args], cwd=cwd or ROOT, check=True, text=True, stdout=subprocess.PIPE,
        timeout=180, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    ).stdout.strip()


def fetch_json(url):
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": f"{OWNER}-app-catalog"}
    if token := os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code not in RETRYABLE_STATUS or attempt == 3:
                raise RuntimeError(f"GitHub API returned HTTP {error.code}: {url}") from error
        except (urllib.error.URLError, TimeoutError):
            if attempt == 3:
                raise
        time.sleep(2 ** attempt)


def discover_repositories(excluded):
    """Walk every API page instead of relying on search indexing."""
    repositories, page = [], 1
    while True:
        batch = fetch_json(f"https://api.github.com/users/{OWNER}/repos"
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
    paragraph, in_code, in_comment = [], False, False
    for line in (readme.read_text(encoding="utf-8").splitlines() if readme else []):
        line = line.strip()
        in_comment = in_comment or "<!--" in line
        if in_comment:
            in_comment = "-->" not in line
            continue
        if line.startswith(("```", "~~~")):
            in_code = not in_code
            if paragraph:
                break
            continue
        if in_code:
            continue
        if not line or line.startswith(("#", "[", "!", "<", "|", "---", "* ", "- ", ">")):
            if paragraph:
                break
            continue
        paragraph.append(line)
    text = " ".join(paragraph) or fallback or "See the source repository for details."
    # Plain text keeps relative links and unresolved badge references out of the catalog.
    text = re.sub(r"!?\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]*>", "", text)
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    if len(text) > limit:
        text = text[:limit - 1].rsplit(" ", 1)[0] + "…"
    return html.escape(text, quote=False)


def app_metadata(folder):
    """Check the catalog fields; Supervisor still validates the complete app schema."""
    apps = []
    for config in sorted(folder.rglob("config.*")):
        parts = config.relative_to(folder).parts
        if config.name not in CONFIG_NAMES or any(p.startswith(".") or p == "rootfs" for p in parts):
            continue
        if config.is_symlink():
            raise ValueError(f"App configurations must not be symlinks: {config}")
        data = yaml.safe_load(config.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "slug" not in data:
            continue
        for key in ("name", "version", "slug", "description"):
            if not isinstance(data.get(key), str) or not data[key].strip():
                raise ValueError(f"Missing or invalid {key!r} in {config}")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", data["slug"]):
            raise ValueError(f"Invalid app slug in {config}")
        if not isinstance(data.get("arch"), list) or not data["arch"] or not set(data["arch"]) <= ARCHITECTURES:
            raise ValueError(f"Invalid architectures in {config}")
        apps.append({**data, "path": config.parent.relative_to(folder).as_posix()})
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
    url = f"https://github.com/{OWNER}/{name}.git"
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
    apps = app_metadata(folder)
    return {"repository": f"{OWNER}/{name}", "path": path, "branch": branch, "commit": sha,
            "url": f"https://github.com/{OWNER}/{name}",
            "excerpt": readme_excerpt(folder, repo.get("description") or apps[0]["description"], limit),
            "apps": apps}


def render_header(entries):
    apps = [app for entry in entries for app in entry["apps"]]
    architectures = sorted({arch for app in apps for arch in app["arch"]})
    link = f"https://github.com/{CATALOG_REPOSITORY}"
    return badgekit.render([
        badgekit.install_row()[:1],
        [badgekit.workflow(CATALOG_REPOSITORY, "update.yml", "catalog sync",
                           f"{link}/actions/workflows/update.yml"),
         badgekit.static("apps", str(len(apps)), "info"),
         badgekit.static("architectures", " · ".join(architectures), "ok")],
        [badgekit.github("stars", CATALOG_REPOSITORY, "stars", f"{link}/stargazers"),
         badgekit.github("forks", CATALOG_REPOSITORY, "forks", f"{link}/forks"),
         badgekit.github("last-commit", CATALOG_REPOSITORY, "synced", f"{link}/commits/main")],
        badgekit.install_row()[1:],
    ])


def render_catalog(entries):
    sections = []
    for entry in entries:
        sections.extend([f"### [{entry['path']}]({entry['url']})", "", f"> {entry['excerpt']}", ""])
        for app in entry["apps"]:
            changelog = f"{entry['url']}/blob/main/{app['path']}/CHANGELOG.md"
            rows = badgekit.app_rows(app, entry["repository"], ROOT / entry["path"] / app["path"],
                                     with_install=False)
            sections.extend([f"**{app['name']}** · [Changelog]({changelog})", "",
                             badgekit.render(rows), ""])
        sections.extend([f"[Source & documentation]({entry['url']}) · "
                         f"[Pinned commit `{entry['commit'][:7]}`]({entry['url']}/commit/{entry['commit']})", ""])
    return "\n".join(sections).strip() or "No matching apps are currently available."


def render_readme(entries):
    template = (TEMPLATES / "README.md").read_text(encoding="utf-8")
    for placeholder in ("{{BADGES}}", "{{APP_CATALOG}}"):
        if template.count(placeholder) != 1:
            raise ValueError(f"README template must contain exactly one {placeholder} placeholder.")
    return (template.replace("{{BADGES}}", render_header(entries))
            .replace("{{APP_CATALOG}}", render_catalog(entries)))


def repository_yaml():
    metadata = json.loads((TEMPLATES / "repository.json").read_text(encoding="utf-8"))
    if not isinstance(metadata, dict) or set(metadata) - {"name", "url", "maintainer"}:
        raise ValueError("Repository template must contain only name, url and maintainer.")
    if any(not isinstance(value, str) or not value.strip() for value in metadata.values()) or "name" not in metadata:
        raise ValueError("Repository metadata needs a nonempty name and nonempty string values.")
    return yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True)


def main():
    metadata = repository_yaml()
    repositories = discover_repositories(EXCLUDED_REPOSITORIES)
    modules = current_submodules()
    if managed_submodules(modules) and not repositories:
        raise ValueError("Refusing to remove the whole catalog; check the API and exclusions.")
    paths = [project_path(repo["name"]).casefold() for repo in repositories]
    if len(paths) != len(set(paths)):
        raise ValueError("Multiple source repositories resolve to the same app folder.")
    entries = [sync_repository(repo, modules, EXCERPT_MAX_CHARS) for repo in repositories]
    slugs = [app["slug"] for entry in entries for app in entry["apps"]]
    if len(slugs) != len(set(slugs)):
        raise ValueError("Duplicate app slugs would collide in Home Assistant.")
    wanted = {entry["path"] for entry in entries}
    # Remove managed submodules only after every current source validated.
    for path in managed_submodules(current_submodules()):
        if path not in wanted:
            git("rm", "--force", "--", path)
    readme = render_readme(entries)
    (ROOT / "README.md").write_text(readme, encoding="utf-8")
    (ROOT / "repository.yaml").write_text(metadata, encoding="utf-8")
    print(f"Synchronized {len(entries)} repositories and {len(slugs)} apps.")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write(f"## App catalog\n\n{render_catalog(entries)}\n")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError, yaml.YAMLError) as error:
        print(f"Synchronization failed: {error}", file=sys.stderr)
        sys.exit(1)
