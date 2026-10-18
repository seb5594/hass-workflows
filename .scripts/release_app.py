"""Publish only new stable versions after the caller's CI matrix succeeds."""
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

app = Path(sys.argv[1])
config = yaml.safe_load((app / "config.yaml").read_text())
version = str(config["version"])
tag = f"v{version}"
repo = os.environ["GITHUB_REPOSITORY"]
ref = os.environ["GITHUB_REF"]
if ref.startswith("refs/tags/") and ref != f"refs/tags/{tag}":
    raise SystemExit("Release tag must match config.yaml version")
existing = subprocess.run(["gh", "release", "view", tag, "--repo", repo], capture_output=True)
if existing.returncode == 0 and not ref.startswith("refs/tags/"):
    print(f"{tag} is already released; no images are replaced.")
    raise SystemExit(0)
platforms = {"amd64": "linux/amd64", "aarch64": "linux/arm64", "armv7": "linux/arm/v7",
             "armhf": "linux/arm/v6", "i386": "linux/386"}
owner = repo.split("/")[0].lower()
image_name = f"ghcr.io/{owner}/hass-{app.name}"
references = []
assets = Path("dist")
assets.mkdir(exist_ok=True)
for arch in config["arch"]:
    # Replaced: image = f"ghcr.io/{owner}/{arch}-{app.name}:{version}"
    # The release tag follows hass-APPNAMEVERSION-ARCH; the package name stays stable.
    image = f"{image_name}:hass-{app.name}{version}-{arch}"
    # Replaced: buildx built each image again after the CI test build.
    subprocess.run(["docker", "tag", f"local/{app.name}:{arch}", image], check=True)
    subprocess.run(["docker", "push", image], check=True)
    references.append(image)
    (assets / f"hass-{app.name}{version}-{arch}.json").write_text(
        json.dumps({"image": image, "platform": platforms[arch], "version": version}, indent=2) + "\n")
# Supervisor resolves the architecture from this shared multi-platform manifest.
subprocess.run(["docker", "buildx", "imagetools", "create", "--tag", f"{image_name}:{version}",
                *references], check=True)
if existing.returncode != 0:
    notes = app / "CHANGELOG.md"
    args = ["gh", "release", "create", tag, "--repo", repo, "--target", os.environ["GITHUB_SHA"],
            "--title", f"{config['name']} {version}"]
    args += ["--notes-file", str(notes)] if notes.exists() else ["--generate-notes"]
    if "-" in version:   # 1.0.0-beta.4 and similar
        args.append("--prerelease")
    subprocess.run([*args, *map(str, sorted(assets.glob("*.json")))], check=True)
# The catalog checks out and validates the app sources; it does not need image credentials.
env = dict(os.environ, GH_TOKEN=os.environ["ORCHESTRATION_TOKEN"])
subprocess.run(["gh", "api", "repos/seb5594/Home-Assistant-Apps/dispatches", "--input", "-"],
               input=json.dumps({"event_type": "update-addons", "client_payload": {
                   "repository": repo, "sha": os.environ["GITHUB_SHA"]}}), text=True, env=env, check=True)
