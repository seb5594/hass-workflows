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

VERSION = re.compile(r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?")
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


def check_hacs(hacs, domain, version):
    """Validate hacs.json against the archive the engine builds; returns warnings for CI.

    `zip_release` is optional. With it HACS installs the ZIP of a *stable* release only: while a
    repository has pre-releases alone, HACS falls back to the branch, builds a release URL that
    does not exist and the download fails. Without it HACS copies the component folder from the
    repository, which works at any time. The ZIP is built and attached to every release anyway,
    for manual installs.
    """
    if hacs.get("zip_release"):
        assert hacs.get("filename") == f"{domain}.zip", f"hacs.json `filename` must be {domain}.zip"
    warnings = []
    if hacs.get("zip_release") and is_prerelease(version):
        warnings.append("hacs.json sets zip_release, but this version is a pre-release: HACS installs "
                        "ZIP releases from stable releases only, so installing fails until one exists. "
                        "Remove `zip_release` and `filename` from hacs.json until then.")
    return warnings


def checksum_line(archives):
    """The closing line of the release notes: each archive with its SHA-256."""
    return "; ".join(f"SHA256 `{path.name}`: `{hashlib.sha256(path.read_bytes()).hexdigest()}`"
                     for path in sorted(archives))


def publish(tag, manifest, out):
    repo = os.environ["GITHUB_REPOSITORY"]
    if subprocess.run(["gh", "release", "view", tag, "--repo", repo],
                      capture_output=True).returncode == 0:
        # Published versions are immutable; bump the manifest for the next release.
        print(f"{tag} already exists; keeping its assets unchanged.")
        return
    archives = sorted(out.glob("*.zip"))
    notes = f"{generated_notes(repo, tag, os.environ['GITHUB_SHA'])}\n\n{checksum_line(archives)}".lstrip()
    run("gh", "release", "create", tag, "--repo", repo, "--target", os.environ["GITHUB_SHA"],
        "--title", release_title(manifest["version"]), "--notes-file", "-",
        *release_flags(manifest["version"]), *map(str, archives), input=notes, text=True)


def main(options):
    project = projectmeta.discover()
    assert project.kind == projectmeta.INTEGRATION, "Packaging needs an integration"
    folder, manifest, hacs = project.folder, project.metadata, project.hacs
    domain, version = project.slug, project.version
    assert domain == folder.name
    assert VERSION.fullmatch(version), "Use X.Y.Z or a PEP 440 a/b/rc pre-release"
    for warning in check_hacs(hacs, domain, version):
        print(f"::warning title=HACS zip_release::{warning}")
    archive = f"{domain}.zip"
    tag = f"v{version}"
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
        publish(tag, manifest, out)
        gitops.notify(config.EVENTS["integrations"], config.INTEGRATIONS_CATALOG,
                      os.environ.get("ORCHESTRATION_TOKEN"))


if __name__ == "__main__":
    main(sys.argv[1:])
