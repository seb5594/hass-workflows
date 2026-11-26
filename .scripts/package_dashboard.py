#!/usr/bin/env python3
"""Build and publish a dashboard project: a Lovelace card as one JavaScript file, or a theme.

    package_dashboard.py            build the card and check the file HACS will install
    package_dashboard.py --check    only validate the metadata
    package_dashboard.py --release  build when needed, then publish the GitHub release

HACS installs a card from the release asset named like `filename` in hacs.json, so the release carries
exactly that file, with its SHA-256 at the end of the notes. A theme has nothing to build: HACS copies
its `themes` folder, and the release only marks the version.
"""
import os
import sys
from pathlib import Path

import config
import gitops
import metrics
import package_integration
import projectmeta
from common import release_tag, run

OUT = Path("dist")


def build(project):
    """Run the project's own build script and return the file it wrote for HACS."""
    asset = OUT / project.hacs["filename"]
    if not asset.is_file():
        run("npm", "run", "build")
    assert asset.is_file(), f"`npm run build` must write {asset}, the file named in hacs.json"
    return asset


def notification_target():
    """Who learns about a release: the dashboard catalog, or the hub directly while there is no catalog."""
    if "dashboards" in config.UNCATALOGUED:
        return config.EVENTS["hub"], config.HUB_REPOSITORY
    return config.EVENTS["dashboards"], config.DASHBOARDS_CATALOG


def main(options):
    project = projectmeta.discover()
    assert project.kind == projectmeta.DASHBOARD, "Packaging needs a dashboard project"
    tag = release_tag(project.version)
    ref = os.environ.get("GITHUB_REF", "")
    if ref.startswith("refs/tags/"):
        assert ref == f"refs/tags/{tag}", "Tag and package.json version must agree"
    if "--check" in options:
        print(f"Validated {project.slug} {project.version}")
        return
    OUT.mkdir(exist_ok=True)
    if project.category == projectmeta.CARD:
        asset = build(project)
        metrics.record("bundle_size", asset.stat().st_size)
        print(package_integration.checksum_line([asset]))
    if "--release" in options:
        package_integration.publish(tag, {"version": project.version}, project.hacs, OUT, "*.js")
        event, repository = notification_target()
        gitops.notify(event, repository, os.environ.get("ORCHESTRATION_TOKEN"))


if __name__ == "__main__":
    main(sys.argv[1:])
