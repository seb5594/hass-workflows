#!/usr/bin/env python3
"""The files every repository keeps in step with the engine, each rendered from one template.

    managed.py sync  KIND [REF] [DIR]  write them; workflows follow engine REF (`main` by default,
                                       or a commit SHA to freeze a repository on one engine state)
    managed.py check KIND [DIR]        fail when one differs from what the engine would write
                                       (a repository that follows `main` only gets a warning, since
                                       the engine moves on without a commit in the repository)

KIND is one of WORKFLOWS below. DIR defaults to the current directory. GitHub reads these files
from each repository, so they cannot be shared by reference; generating them from templates keeps
them identical everywhere and lets CI fail on drift.
"""
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import config
import projectmeta
import templating
import upstream

TEMPLATES = config.ENGINE_ROOT / ".templates"
SNIPPETS = TEMPLATES / "snippets"
FOLLOW = "main"
PIN = re.compile(r"ref: ([0-9a-f]{40}|main)\n")


@dataclass(frozen=True)
class Workflow:
    template: str
    target: str
    values: dict


# kind -> the workflow that pins the engine; its template lives in .templates/callers
WORKFLOWS = {
    "app": Workflow("project", ".github/workflows/ci.yml",
                    {"TIMEOUT": "90", "PACKAGES": "  packages: write"}),
    "integration": Workflow("project", ".github/workflows/ci.yml",
                            {"TIMEOUT": "30", "PACKAGES": ""}),
    "catalog-apps": Workflow("catalog", ".github/workflows/update.yml",
                             {"KIND": "apps", "TITLE": "app", "EVENT": config.EVENTS["apps"]}),
    "catalog-integrations": Workflow("catalog-sync", ".github/workflows/update.yml", {}),
    "hub": Workflow("hub", ".github/workflows/update.yml", {"EVENT": config.EVENTS["hub"]}),
}
# Apps that package a released image keep this workflow: it follows the upstream releases.
UPSTREAM = Workflow("upstream", ".github/workflows/upstream.yml", {})
FOLLOWED_PIN = re.compile(r"^# renovate: datasource=docker depName=(?:docker\.io|ghcr\.io)/\S+\nARG \w+=v?\d+\.\d+\.\d+$",
                          re.M)
# Integrations with tests against a real Home Assistant core also keep this workflow.
COMPATIBILITY = Workflow("compat", ".github/workflows/compat.yml", {})
CATALOG_RELEASE = Workflow("catalog-release", ".github/workflows/release.yml", {})

# Manual submission of an integration to the official HACS default catalog.
MARKETPLACE = Workflow("marketplace-catalog", ".github/workflows/marketplace-catalog.yml", {})

# What differs between the two catalogs in their maintenance notes.
CATALOG_NOTES = {
    "catalog-apps": {
        "OUTPUT": "the README, `repository.yaml` and the submodules",
        "NAMES": "`Home-Assistant-<project>-App`, `Home-Assistant-<project>-Apps` or `Home-Assistant-<project>-Addon`",
        "REQUIREMENT": "with at least one app configuration, at the root or in a nested folder",
        "TITLE": "app", "EVENT": config.EVENTS["apps"],
        "PINNING": ("Each run pins the latest default-branch commit of every listed app as a Git "
                    "submodule, because the Supervisor installs from the repository tree."),
    },
}


def read_template(name):
    return (TEMPLATES / name).read_text()


def render_workflow(workflow, sha):
    text = templating.expand_includes(read_template(f"callers/{workflow.template}.yml.tpl"), SNIPPETS)
    return templating.fill(text, {**workflow.values, "ENGINE_REPOSITORY": config.ENGINE_REPOSITORY,
                                  "ENGINE_SHA": sha}, templating.DUNDER, once=False)


def renovate_config():
    """The shared Renovate preset, written out in full.

    A repository cannot extend the preset of this private engine: Renovate does not load private
    presets for public repositories and reports "Cannot find preset's package". Each repository
    therefore carries the complete preset, generated from default.json.
    """
    preset = json.loads((config.ENGINE_ROOT / "default.json").read_text())
    return json.dumps(preset, indent=2) + "\n"


def shared_files():
    """Identical in every repository, whatever it contains."""
    return {
        ".github/dependabot.yml": read_template("dependabot.yml"),
        ".github/renovate.json": renovate_config(),
        ".github/FUNDING.yml": templating.fill(read_template("FUNDING.yml"), {
            "COFFEE_USER": config.COFFEE_USER, "PAYPAL_URL": config.PAYPAL_URL}),
    }


def offered_to_default_catalog(root):
    """Every integration except those listed in config.DEFAULT_CATALOG_EXCLUDED."""
    name = projectmeta.discover(Path(root)).repository.split("/")[-1]
    return name not in config.DEFAULT_CATALOG_EXCLUDED


def expected(kind, sha, root=Path(".")):
    """Path (relative to the repository) -> content for every file the engine manages in `kind`."""
    files = shared_files()
    files[WORKFLOWS[kind].target] = render_workflow(WORKFLOWS[kind], sha)
    if kind == "app":
        if all(app.metadata.get("image") for app in projectmeta.app_projects(root)):
            target = WORKFLOWS[kind].target
            files[target] = files[target].replace(
                "          draft: ${{ inputs.draft }}",
                "          draft: ${{ inputs.draft }}\n          multiarch-only: 'true'",
            )
        if upstream.policy(root):
            preset = json.loads(files[".github/renovate.json"])
            preset["packageRules"].append({
                "description": "Major Docker updates require dashboard approval and manual merge",
                "matchDatasources": ["docker"],
                "matchUpdateTypes": ["major"],
                "dependencyDashboardApproval": True,
                "automerge": False,
                "groupName": None,
                "separateMajorMinor": True,
            })
            files[".github/renovate.json"] = json.dumps(preset, indent=2) + "\n"
        for app in projectmeta.app_projects(root):
            folder = app.folder
            entrypoint = folder / "entrypoint.sh"
            if entrypoint.exists():  # apps on the base image's s6-overlay start without one
                files[entrypoint.relative_to(root).as_posix()] = read_template("entrypoint.sh")
            dockerfile = folder / "Dockerfile"
            if dockerfile.is_file() and FOLLOWED_PIN.search(dockerfile.read_text()):
                files[UPSTREAM.target] = render_workflow(UPSTREAM, sha)
    elif kind == "integration" and (root / ".github/ha_tests").is_dir():
        files[COMPATIBILITY.target] = render_workflow(COMPATIBILITY, sha)
    elif kind == "catalog-integrations":
        files[COMPATIBILITY.target] = render_workflow(COMPATIBILITY, sha)
        files[CATALOG_RELEASE.target] = render_workflow(CATALOG_RELEASE, sha)
        files[".github/workflows/ci.yml"] = read_template("callers/catalog-checks.yml.tpl")
    elif kind in CATALOG_NOTES:
        files[".github/DEVELOPMENT.md"] = templating.fill(
            read_template("catalog/DEVELOPMENT.md"), CATALOG_NOTES[kind], once=False)
    if kind == "integration":
        repository = projectmeta.discover(Path(root)).repository
        from common import is_calendar_version
        if (config.INTEGRATION_TAG_PREFIXES.get(repository, "v") == ""
                or is_calendar_version(projectmeta.discover(Path(root)).version)):
            target = WORKFLOWS[kind].target
            files[target] = files[target].replace("tags: ['v*']", "tags: ['[0-9]*']")
    if kind == "app":
        from common import is_calendar_version
        if is_calendar_version(projectmeta.discover(Path(root)).version):
            target = WORKFLOWS[kind].target
            files[target] = files[target].replace("tags: ['v*']", "tags: ['[0-9]*']")
    if kind == "integration" and offered_to_default_catalog(root):
        files[MARKETPLACE.target] = render_workflow(MARKETPLACE, sha)
        if repository == "seb5594/hass-google_translator-integration":
            files[MARKETPLACE.target] = files[MARKETPLACE.target].replace(
                "default: false", "default: true"
            ).replace(
                "secrets.CATALOG_SUBMISSION_TOKEN }}",
                "secrets.CATALOG_SUBMISSION_TOKEN || secrets.ORCHESTRATION_PAT }}",
            )
    return files


def pinned_sha(kind, root="."):
    workflow = Path(root) / WORKFLOWS[kind].target
    found = PIN.search(workflow.read_text())
    if not found:
        raise ValueError(f"{workflow} must follow the engine branch `{FOLLOW}` or pin a commit SHA")
    return found.group(1)


def check(kind, root="."):
    """Every managed file must equal its template, rendered for the engine commit the workflow pins."""
    root = Path(root)
    ref = pinned_sha(kind, root)
    differing = [path for path, text in expected(kind, ref, root).items()
                 if not (root / path).is_file() or (root / path).read_text() != text]
    if differing and ref == FOLLOW:
        print(f"::warning::Files differ from the current engine templates, run "
              f"`managed.py sync {kind}`: {', '.join(sorted(differing))}")
    elif differing:
        raise ValueError(f"Files differ from the engine templates (run managed.py sync): "
                         f"{', '.join(sorted(differing))}")


def sync(kind, sha=FOLLOW, root="."):
    """Write the managed files; returns the paths that changed."""
    root = Path(root)
    changed = []
    for path, text in expected(kind, sha, root).items():
        target = root / path
        if target.is_file() and target.read_text() == text:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        changed.append(path)
    return changed


def main(arguments):
    command, kind, *rest = arguments
    if kind not in WORKFLOWS:
        raise SystemExit(f"Unknown kind {kind!r}; choose one of {', '.join(WORKFLOWS)}")
    if command == "sync":
        changed = sync(kind, *rest)
        print("updated: " + ", ".join(changed) if changed else "unchanged")
    elif command == "check":
        check(kind, *rest)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
