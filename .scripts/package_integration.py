"""Create deterministic, validated HACS and manual installation ZIP archives."""
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import config
import gitops
import metrics
import projectmeta
from common import generated_notes, is_prerelease, release_flags, release_title, run

# X.Y.Z, or X.Y.Z.B for projects that keep a build number such as 2026.10.20.0.
VERSION = re.compile(r"\d+\.\d+\.\d+(?:\.\d+)?(?:(?:a|b|rc)\d+)?")
ARCHIVE_DATE = (2020, 1, 1, 0, 0, 0)


def write_archive(path, files, folder, prefix):
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        for file in files:
            info = ZipInfo(prefix + file.relative_to(folder).as_posix(), ARCHIVE_DATE)
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, file.read_bytes())
    with ZipFile(path) as archive:
        assert archive.testzip() is None
        assert prefix + "manifest.json" in archive.namelist()


def check_hacs(hacs, domain):
    """`zip_release` is optional; when set, `filename` must be the archive the engine builds."""
    if hacs.get("zip_release"):
        assert hacs.get("filename") == f"{domain}.zip", f"hacs.json `filename` must be {domain}.zip"


def checksum_line(archives):
    """The closing line of the release notes: each archive with its SHA-256."""
    return "; ".join(f"SHA256 `{path.name}`: `{hashlib.sha256(path.read_bytes()).hexdigest()}`"
                     for path in sorted(archives))


def gh_json(*args):
    result = subprocess.run(["gh", *args], capture_output=True, text=True)
    return json.loads(result.stdout) if result.returncode == 0 else None


def stable_version_released(repo):
    """Has a release of a stable version (not 1.0.0b3 and the like) been published?"""
    releases = gh_json("release", "list", "--repo", repo, "--limit", "100", "--json", "tagName,isDraft") or []
    return any(not release["isDraft"] and not is_prerelease(release["tagName"].removeprefix("v"))
               for release in releases)


def marked_prerelease(hacs, version, repo):
    """Whether the release of `version` carries GitHub's pre-release marker.

    HACS installs (and counts the downloads of) a `zip_release` ZIP from stable releases only.
    Until a stable version exists, the newest beta is therefore published as a regular release;
    afterwards betas are marked again, and HACS offers them behind its beta switch.
    """
    if not is_prerelease(version):
        return False
    return not (hacs.get("zip_release") and not stable_version_released(repo))


def publish(tag, manifest, hacs, out):
    repo = os.environ["GITHUB_REPOSITORY"]
    prerelease = marked_prerelease(hacs, manifest["version"], repo)
    existing = gh_json("release", "view", tag, "--repo", repo, "--json", "isPrerelease")
    if existing is not None:
        # Published versions are immutable; bump the manifest for the next release. Only the
        # pre-release marker may follow the rule above, e.g. for a beta released before it applied.
        edits = []
        if existing["isPrerelease"] != prerelease:
            edits.append(f"--prerelease={str(prerelease).lower()}")
        # Switching the marker by edit does not make GitHub pick a new "latest" release, and
        # catalogs and installers read exactly that one: repair it when the repository has none.
        if not prerelease and gh_json("api", f"repos/{repo}/releases/latest") is None:
            edits.append("--latest")
        if edits:
            run("gh", "release", "edit", tag, "--repo", repo, *edits)
        print(f"{tag} already exists; keeping its assets unchanged.")
        return
    archives = sorted(out.glob("*.zip"))
    notes = f"{generated_notes(repo, tag, os.environ['GITHUB_SHA'])}\n\n{checksum_line(archives)}".lstrip()
    run("gh", "release", "create", tag, "--repo", repo, "--target", os.environ["GITHUB_SHA"],
        "--title", release_title(manifest["version"]) if is_prerelease(manifest["version"]) else tag,
        "--notes-file", "-",
        *release_flags(manifest["version"], prerelease), *map(str, archives), input=notes, text=True)


def main(options):
    project = projectmeta.discover()
    assert project.kind == projectmeta.INTEGRATION, "Packaging needs an integration"
    folder, manifest, hacs = project.folder, project.metadata, project.hacs
    domain, version = project.slug, project.version
    assert domain == folder.name
    assert VERSION.fullmatch(version), "Use X.Y.Z or X.Y.Z.B, optionally with a PEP 440 a/b/rc pre-release"
    check_hacs(hacs, domain)
    archive = f"{domain}.zip"
    tag = f"{config.INTEGRATION_TAG_PREFIXES.get(project.repository, 'v')}{version}"
    ref = os.environ.get("GITHUB_REF", "")
    if ref.startswith("refs/tags/"):
        assert ref == f"refs/tags/{tag}", "Tag and manifest version must agree"
    if "--check" in options:
        print(f"Validated {domain} {version}")
        return
    out = Path("dist")
    out.mkdir(exist_ok=True)
    files = sorted(p for p in folder.rglob("*") if p.is_file()
                   and "__pycache__" not in p.parts and p.suffix not in {".pyc", ".pyo"})
    # One ZIP serves HACS and manual installs: its content is the component folder itself.
    write_archive(out / archive, files, folder, "")
    metrics.record("zip_size", (out / archive).stat().st_size)
    print(checksum_line(out.glob("*.zip")))
    if "--release" in options:
        publish(tag, manifest, hacs, out)
        gitops.notify(config.EVENTS["integrations"], config.INTEGRATIONS_CATALOG,
                      os.environ.get("ORCHESTRATION_TOKEN"))


if __name__ == "__main__":
    main(sys.argv[1:])
