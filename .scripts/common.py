"""Constants and helpers shared by the engine scripts."""
import base64
import json
import os
import subprocess
import sys

PLATFORMS = {
    "amd64": "linux/amd64",
    "aarch64": "linux/arm64",
    "armv7": "linux/arm/v7",
    "armhf": "linux/arm/v6",
    "i386": "linux/386",
}


def image_tag(slug, version, arch=None):
    """Return ARCH-hass-SLUG-vVERSION; multi-arch images carry no ARCH prefix."""
    stem = f"hass-{slug}-v{version}"
    return f"{arch}-{stem}" if arch else stem


def image_repository(owner, slug):
    return f"ghcr.io/{owner.lower()}/hass-{slug}"


def release_flags():
    """Extra `gh release create` flags; RELEASE_DRAFT=true keeps a release private."""
    return ["--draft"] if os.environ.get("RELEASE_DRAFT", "").lower() == "true" else []


def run(*args, **kwargs):
    subprocess.run(args, check=True, **kwargs)


def run_captured(*args, **kwargs):
    """Run a command, echo its output live and return it for later parsing."""
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, **kwargs)
    lines = []
    for line in process.stdout:
        sys.stdout.write(line)
        lines.append(line)
    if process.wait():
        raise subprocess.CalledProcessError(process.returncode, args)
    return "".join(lines)


def notify_catalog(catalog_repository, event_type, source_repository):
    """Ask a catalog repository to refresh; without a token the hourly run catches up."""
    token = os.environ.get("ORCHESTRATION_TOKEN")
    if not token:
        print("No ORCHESTRATION_TOKEN; the catalog picks this version up on its hourly run.")
        return
    payload = {"event_type": event_type, "client_payload": {
        "repository": source_repository, "sha": os.environ["GITHUB_SHA"]}}
    subprocess.run(["gh", "api", f"repos/{catalog_repository}/dispatches", "--input", "-"],
                   input=json.dumps(payload), text=True, check=True,
                   env=dict(os.environ, GH_TOKEN=token))


def authenticated_git(token):
    """`git` command prefix that authenticates github.com requests without storing credentials."""
    credentials = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return ["git", "-c", f"http.https://github.com/.extraheader=AUTHORIZATION: basic {credentials}",
            "-c", "user.name=github-actions[bot]",
            "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com"]
