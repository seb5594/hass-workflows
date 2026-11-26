"""Helpers shared by the engine scripts: image names, release flags and subprocess wrappers."""
import json
from pathlib import Path
import os
import re
import shlex
import subprocess
import sys


def is_calendar_version(version):
    """Recognize date versions, including legacy dashed dates and build suffixes."""
    return bool(re.fullmatch(r"20\d{2}[.-]\d{1,2}[.-]\d{1,2}(?:\.\d+)?", str(version)))


def release_tag(version, prefix="v"):
    """Date versions publish without a prefix across integrations and apps."""
    return str(version) if is_calendar_version(version) else f"{prefix}{version}"


def image_tag(slug, version, arch=None):
    """Return ARCH-hass-SLUG-vVERSION; multi-arch images carry no ARCH prefix."""
    stem = f"hass-{slug}-v{version}"
    return f"{arch}-{stem}" if arch else stem


PACKAGE_SUFFIX = "-app"


def image_repository(owner, slug):
    # A repository move may need a fresh GHCR package without changing the HA slug.
    # Existing projects keep their original registry names unless explicitly mapped.
    path = Path('.github/images.json')
    aliases = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(aliases, dict) or any(not isinstance(key,str) or not isinstance(value,str)
            or not re.fullmatch(r'[a-z0-9]+(?:[._-][a-z0-9]+)*',value) for key,value in aliases.items()):
        raise ValueError('.github/images.json must map app slugs to lowercase GHCR package names')
    if len(set(aliases.values())) != len(aliases):
        raise ValueError('App registry package names must be distinct')
    package = aliases.get(slug, f"hass-{slug}")
    # Every app package ends in -app, so it is recognisable among the other images of a Docker host.
    return f"ghcr.io/{owner.lower()}/{package if package.endswith(PACKAGE_SUFFIX) else package + PACKAGE_SUFFIX}"


# App versions carry a dash suffix (1.0.0-beta4), integrations a PEP 440 one (1.0.0b1).
PRERELEASE = re.compile(r"-|(?:a|b|rc)\d+$")


def is_prerelease(version):
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:\.\d+)?|\d{4}\.\d{2}\.\d{2}\.\d+", version):
        return False
    return bool(PRERELEASE.search(version))


STAGE_NAMES = {"a": "Alpha", "b": "Beta", "rc": "RC"}
PEP440_STAGE = re.compile(r"\d+\.\d+\.\d+(?:\.\d+)?(a|b|rc)(\d+)")
DASHED_STAGE = re.compile(r"\d+\.\d+(?:\.\d+)?-([A-Za-z]+)[.-]?(\d+)?")


def release_title(version):
    """The title of a GitHub release: `v1.2.0`, or for a pre-release only its stage, e.g. `Beta 3`.

    The numeric part of a pre-release version only keeps the git tag a proper version; the
    release itself is known by its stage.
    """
    if found := PEP440_STAGE.fullmatch(version):
        return f"{STAGE_NAMES[found[1]]} {found[2]}"
    if found := DASHED_STAGE.fullmatch(version):
        name = "RC" if found[1].lower() == "rc" else found[1].capitalize()
        return f"{name} {found[2]}" if found[2] else name
    return release_tag(version)


def generated_notes(repo, tag, target):
    """GitHub's automatic release notes for a tag that is about to be created."""
    return subprocess.run(
        ["gh", "api", f"repos/{repo}/releases/generate-notes", "-f", f"tag_name={tag}",
         "-f", f"target_commitish={target}", "--jq", ".body"],
        check=True, capture_output=True, text=True).stdout.strip()


def release_flags(version="", prerelease=None):
    """Extra `gh release create` flags: pre-release marker, and RELEASE_DRAFT=true keeps a release private.

    The marker follows the version unless the caller decides otherwise with `prerelease`. A stable
    release is pinned as the latest explicitly: a four-part calendar version (2026.11.25.14) is not
    valid semantic versioning, so without this GitHub is left to guess which release is the latest
    and can keep an older one pinned — which is what catalogs and installers read.
    """
    marked = is_prerelease(version) if prerelease is None else prerelease
    draft = os.environ.get("RELEASE_DRAFT", "").lower() == "true"
    flags = []
    if marked:
        flags.append("--prerelease")
    elif not draft:
        flags.append("--latest")
    if draft:
        flags.append("--draft")
    return flags


ANNOTATION_TAIL_LINES = 15
ANNOTATION_COMMAND_CHARS = 300


def annotate_failure(args, returncode, output_lines=()):
    """Report a failed command as a GitHub error annotation.

    Annotations show up on the run page and through the API, so the reason for a red run can be
    read without opening the full log. Nested scripts annotate their own failing command first,
    which is the most specific one.
    """
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    command = shlex.join(str(arg) for arg in args)[:ANNOTATION_COMMAND_CHARS]
    message = f"{command} exited with {returncode}"
    if tail := [line.rstrip() for line in output_lines][-ANNOTATION_TAIL_LINES:]:
        message += "\n" + "\n".join(tail)
    # Workflow commands need their line breaks and percent signs escaped.
    escaped = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::error title=Command failed::{escaped}", flush=True)


def run(*args, **kwargs):
    try:
        subprocess.run(args, check=True, **kwargs)
    except subprocess.CalledProcessError as error:
        annotate_failure(args, error.returncode)
        raise


def run_captured(*args, **kwargs):
    """Run a command, echo its output live and return it for later parsing."""
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, **kwargs)
    lines = []
    for line in process.stdout:
        sys.stdout.write(line)
        lines.append(line)
    if process.wait():
        annotate_failure(args, process.returncode, lines)
        raise subprocess.CalledProcessError(process.returncode, args)
    return "".join(lines)
