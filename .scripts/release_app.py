"""Publish new stable app versions once the caller's CI matrix has succeeded."""
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

from common import PLATFORMS, image_repository, image_tag, notify_catalog, release_flags, run

CATALOG_REPOSITORY = "seb5594/Home-Assistant-Apps"


def release_exists(tag, repo):
    return subprocess.run(["gh", "release", "view", tag, "--repo", repo],
                          capture_output=True).returncode == 0


def push_architecture_images(config, folder, repository, assets):
    references = []
    for arch in config["arch"]:
        tag = image_tag(config["slug"], config["version"], arch)
        image = f"{repository}:{tag}"
        # The CI build already produced and tested this image; retag instead of rebuilding.
        run("docker", "tag", f"local/{folder.name}:{arch}", image)
        run("docker", "push", image)
        references.append(image)
        (assets / f"{tag}.json").write_text(json.dumps(
            {"image": image, "platform": PLATFORMS[arch], "version": config["version"]},
            indent=2) + "\n")
    return references


def create_release(config, folder, repo, tag, assets):
    notes = folder / "CHANGELOG.md"
    args = ["gh", "release", "create", tag, "--repo", repo, "--target", os.environ["GITHUB_SHA"],
            "--title", f"{config['name']} {config['version']}", *release_flags()]
    args += ["--notes-file", str(notes)] if notes.exists() else ["--generate-notes"]
    run(*args, *map(str, sorted(assets.glob("*.json"))))


def main(app):
    folder = Path(app)
    config = yaml.safe_load((folder / "config.yaml").read_text())
    config["version"] = str(config["version"])
    repo, ref = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_REF"]
    tag = f"v{config['version']}"
    if ref.startswith("refs/tags/") and ref != f"refs/tags/{tag}":
        raise SystemExit("Release tag must match config.yaml version")
    exists = release_exists(tag, repo)
    if exists and not ref.startswith("refs/tags/"):
        print(f"{tag} is already released; no images are replaced.")
        return
    repository = image_repository(repo.split("/")[0], config["slug"])
    assets = Path("dist")
    assets.mkdir(exist_ok=True)
    references = push_architecture_images(config, folder, repository, assets)
    # One multi-arch manifest lets Docker pick the right architecture by itself.
    run("docker", "buildx", "imagetools", "create", "--tag",
        f"{repository}:{image_tag(config['slug'], config['version'])}",
        "--tag", f"{repository}:latest", *references)
    if not exists:
        create_release(config, folder, repo, tag, assets)
    notify_catalog(CATALOG_REPOSITORY, "update-addons", repo)


if __name__ == "__main__":
    main(sys.argv[1])
