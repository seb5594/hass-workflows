"""Publish new stable app versions once the caller's CI matrix has succeeded."""
import json
import os
import subprocess
import sys
import time
import tempfile
from pathlib import Path

import yaml

import config
import gitops
import legacy
from common import generated_notes, image_repository, image_tag, is_prerelease, release_flags, release_title, run


def release_exists(tag, repo):
    return subprocess.run(["gh", "release", "view", tag, "--repo", repo],
                          capture_output=True).returncode == 0


def push_image(image):
    """Retry short-lived GHCR layer errors without rebuilding the tested image."""
    for attempt in range(4):
        try:
            run("docker", "push", image)
            return
        except subprocess.CalledProcessError:
            if attempt == 3:
                raise
            delay = 2 ** attempt
            print(f"Registry push failed; retrying {image} in {delay}s (attempt {attempt + 2}/4).")
            time.sleep(delay)


def push_architecture_images(app_config, folder, repository, assets):
    references = []
    for arch in app_config["arch"]:
        tag = image_tag(app_config["slug"], app_config["version"], arch)
        image = f"{repository}:{tag}"
        # The CI build already produced and tested this image; retag instead of rebuilding.
        run("docker", "tag", f"local/{folder.name}:{arch}", image)
        # Replaced: run("docker", "push", image)
        push_image(image)
        references.append(image)
        (assets / f"{tag}.json").write_text(json.dumps(
            {"image": image, "platform": config.PLATFORMS[arch], "version": app_config["version"]},
            indent=2) + "\n")
    return references


def push_platform_digests(app_config, folder, repository, assets):
    """Export cached platform builds directly to the shared image repository."""
    references = []
    dockerfile = (folder / "Dockerfile").read_text()
    for arch in app_config["arch"]:
        with tempfile.TemporaryDirectory() as temporary:
            metadata = Path(temporary) / "metadata.json"
            run(
                "docker", "buildx", "build", "--platform", config.PLATFORMS[arch],
                "--build-arg", f"BUILD_ARCH={arch}",
                "--build-arg", f"BUILD_VERSION={app_config['version']}",
                *legacy.build_args(arch, dockerfile),
                "--provenance=false", "--sbom=false",
                "--output", f"type=image,name={repository},push-by-digest=true,name-canonical=true,push=true",
                "--metadata-file", str(metadata), str(folder),
            )
            digest = json.loads(metadata.read_text())["containerimage.digest"]
        references.append(f"{repository}@{digest}")
    (assets / f"{app_config['slug']}-image.json").write_text(json.dumps({
        "image": f"{repository}:{image_tag(app_config['slug'], app_config['version'])}",
        "platforms": [config.PLATFORMS[arch] for arch in app_config["arch"]],
        "version": app_config["version"],
    }, indent=2) + "\n")
    return references


def create_release(app_config, folder, repo, tag, assets):
    target = os.environ["GITHUB_SHA"]
    notes = generated_notes(repo, tag, target, folder / "CHANGELOG.md")
    args = ["gh", "release", "create", tag, "--repo", repo, "--target", target,
            "--title", release_title(app_config["version"]), *release_flags(app_config["version"])]
    run(*args, "--notes-file", "-", *map(str, sorted(assets.glob("*.json"))), input=notes, text=True)


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
    from common import release_tag
    tag = release_tag(app_config["version"])
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
        publisher = push_platform_digests if os.environ.get("MULTIARCH_ONLY") == "true" else push_architecture_images
        references = publisher(metadata, member, repository, assets)
        # One multi-arch manifest per app lets Docker pick its architecture.
        tags = [image_tag(metadata["slug"], metadata["version"])]
        if os.environ.get("MULTIARCH_ONLY") == "true":
            tags.append(metadata["version"])
        if not is_prerelease(metadata["version"]):
            tags.append("latest")
        run("docker", "buildx", "imagetools", "create",
            *(option for tag in tags for option in ("--tag", f"{repository}:{tag}")), *references)
    if not exists:
        create_release(app_config, folder, repo, tag, assets)
    gitops.notify(config.EVENTS["apps"], config.APPS_CATALOG, os.environ.get("ORCHESTRATION_TOKEN"))


if __name__ == "__main__":
    main(*sys.argv[1:])
