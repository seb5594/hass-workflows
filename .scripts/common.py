"""Helpers shared by the engine scripts: image names, release flags and subprocess wrappers."""
import os
import shlex
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
