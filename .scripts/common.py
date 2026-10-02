"""Helpers shared by the engine scripts: image names, release flags and subprocess wrappers."""
import os
import subprocess
import sys


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
