"""Create deterministic, validated HACS and manual installation ZIP archives."""
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import metrics
from common import release_flags, run

VERSION = re.compile(r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?")
PRERELEASE = re.compile(r"(?:a|b|rc)\d+$")
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


def publish(tag, manifest, out):
    repo = os.environ["GITHUB_REPOSITORY"]
    if subprocess.run(["gh", "release", "view", tag, "--repo", repo],
                      capture_output=True).returncode == 0:
        # Published versions are immutable; bump the manifest for the next release.
        print(f"{tag} already exists; keeping its assets unchanged.")
        return
    flags = ["--prerelease"] if PRERELEASE.search(manifest["version"]) else []
    run("gh", "release", "create", tag, "--repo", repo, "--target", os.environ["GITHUB_SHA"],
        "--title", f"{manifest['name']} {manifest['version']}", "--generate-notes",
        *flags, *release_flags(), *map(str, sorted(out.iterdir())))


def main(options):
    manifests = list(Path("custom_components").glob("*/manifest.json"))
    assert len(manifests) == 1, "Exactly one integration is expected"
    folder = manifests[0].parent
    manifest = json.loads(manifests[0].read_text())
    domain, version = manifest["domain"], manifest["version"]
    assert domain == folder.name
    assert VERSION.fullmatch(version), "Use X.Y.Z or a PEP 440 a/b/rc pre-release"
    hacs = json.loads(Path("hacs.json").read_text())
    assert hacs["zip_release"] is True and hacs["filename"] == f"{domain}.zip"
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
    for name, prefix in [(hacs["filename"], ""),
                         (f"{domain}-{version}-manual.zip", f"custom_components/{domain}/")]:
        write_archive(out / name, files, folder, prefix)
    metrics.record("zip_size", (out / hacs["filename"]).stat().st_size)
    checksums = "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n"
                        for p in sorted(out.glob("*.zip")))
    (out / "SHA256SUMS.txt").write_text(checksums)
    print(checksums)
    if "--release" in options:
        publish(tag, manifest, out)


if __name__ == "__main__":
    main(sys.argv[1:])
