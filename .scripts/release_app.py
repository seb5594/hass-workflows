"""Publish new stable app versions once the caller's CI matrix has succeeded."""
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

import config
import gitops
from common import image_repository, image_tag, is_prerelease, release_flags, release_title, run


def release_exists(tag, repo):
    return subprocess.run(["gh", "release", "view", tag, "--repo", repo],
                          capture_output=True).returncode == 0


def push_architecture_images(app_config, folder, repository, assets):
    references = []
    for arch in app_config["arch"]:
        tag = image_tag(app_config["slug"], app_config["version"], arch)
        image = f"{repository}:{tag}"
        # The CI build already produced and tested this image; retag instead of rebuilding.
        run("docker", "tag", f"local/{folder.name}:{arch}", image)
        run("docker", "push", image)
        references.append(image)
        (assets / f"{tag}.json").write_text(json.dumps(
            {"image": image, "platform": config.PLATFORMS[arch], "version": app_config["version"]},
            indent=2) + "\n")
    return references


def create_release(app_config, folder, repo, tag, assets):
    notes = folder / "CHANGELOG.md"
    args = ["gh", "release", "create", tag, "--repo", repo, "--target", os.environ["GITHUB_SHA"],
            "--title", release_title(app_config["version"]), *release_flags(app_config["version"])]
    args += ["--notes-file", str(notes)] if notes.exists() else ["--generate-notes"]
    run(*args, *map(str, sorted(assets.glob("*.json"))))


def main(app, *companions):
    folders = [Path(path) for path in (app, *companions)]
    configs = [yaml.safe_load((folder / "config.yaml").read_text()) for folder in folders]
    for metadata in configs:
        metadata["version"] = str(metadata["version"])
    if len({metadata["version"] for metadata in configs}) != 1:
        raise ValueError("Bundled apps must share the same release version")
    if len({metadata["slug"] for metadata in configs}) != len(configs):
        raise ValueError("Bundled apps must have distinct slugs")
    folder, app_config = folders[0], configs[0]
    repo, ref = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_REF"]
    tag = f"v{app_config['version']}"
    if ref.startswith("refs/tags/") and ref != f"refs/tags/{tag}":
        raise SystemExit("Release tag must match config.yaml version")
    exists = release_exists(tag, repo)
    if exists and not ref.startswith("refs/tags/"):
        print(f"{tag} is already released; no images are replaced.")
        gitops.notify(config.EVENTS["apps"], config.APPS_CATALOG, os.environ.get("ORCHESTRATION_TOKEN"))
        return
    assets = Path("dist")
    assets.mkdir(exist_ok=True)
    for member, metadata in zip(folders, configs):
        repository = image_repository(repo.split("/")[0], metadata["slug"])
        references = push_architecture_images(metadata, member, repository, assets)
        # One multi-arch manifest per app lets Docker pick its architecture.
        tags = [image_tag(metadata["slug"], metadata["version"])]
        if not is_prerelease(metadata["version"]):
            tags.append("latest")
        run("docker", "buildx", "imagetools", "create",
            *(option for tag in tags for option in ("--tag", f"{repository}:{tag}")), *references)
    if not exists:
        create_release(app_config, folder, repo, tag, assets)
    gitops.notify(config.EVENTS["apps"], config.APPS_CATALOG, os.environ.get("ORCHESTRATION_TOKEN"))


if __name__ == "__main__":
    main(*sys.argv[1:])
