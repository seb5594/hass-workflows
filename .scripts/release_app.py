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
build_file = app / "build.yaml"
bases = yaml.safe_load(build_file.read_text())["build_from"] if build_file.exists() else {}
owner = repo.split("/")[0].lower()
for arch in config["arch"]:
    image = f"ghcr.io/{owner}/{arch}-{app.name}:{version}"
    args = ["docker", "buildx", "build", "--platform", platforms[arch], "--push", "--tag", image,
            "--provenance=false", "--build-arg", f"BUILD_ARCH={arch}",
            "--build-arg", f"BUILD_VERSION={version}"]
    if arch in bases:
        args += ["--build-arg", f"BUILD_FROM={bases[arch]}"]
    subprocess.run(args + [str(app)], check=True)
if existing.returncode != 0:
    notes = app / "CHANGELOG.md"
    args = ["gh", "release", "create", tag, "--repo", repo, "--target", os.environ["GITHUB_SHA"],
            "--title", f"{config['name']} {version}"]
    args += ["--notes-file", str(notes)] if notes.exists() else ["--generate-notes"]
    subprocess.run(args, check=True)
# The catalog checks out and validates the app sources; it does not need image credentials.
env = dict(os.environ, GH_TOKEN=os.environ["ORCHESTRATION_TOKEN"])
subprocess.run(["gh", "api", "repos/seb5594/Home-Assistant-Apps/dispatches", "--input", "-"],
               input=json.dumps({"event_type": "update-addons", "client_payload": {
                   "repository": repo, "sha": os.environ["GITHUB_SHA"]}}), text=True, env=env, check=True)
