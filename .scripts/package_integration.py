"""Create deterministic, validated HACS and manual installation ZIP archives."""
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

folders = list(Path("custom_components").glob("*/manifest.json"))
assert len(folders) == 1, "Exactly one integration is expected"
folder = folders[0].parent
manifest = json.loads(folders[0].read_text())
domain, version = manifest["domain"], manifest["version"]
assert domain == folder.name
assert re.fullmatch(r"\d+\.\d+\.\d+", version), "Stable semantic version required"
hacs = json.loads(Path("hacs.json").read_text())
assert hacs["zip_release"] is True and hacs["filename"] == f"{domain}.zip"
tag = f"v{version}"
ref = os.environ.get("GITHUB_REF", "")
if ref.startswith("refs/tags/"):
    assert ref == f"refs/tags/{tag}", "Tag and manifest version must agree"
if "--check" in sys.argv:
    print(f"Validated {domain} {version}")
    raise SystemExit(0)
out = Path("dist")
out.mkdir(exist_ok=True)
files = sorted(p for p in folder.rglob("*") if p.is_file()
               and "__pycache__" not in p.parts and p.suffix not in {".pyc", ".pyo"})
for name, prefix in [(hacs["filename"], ""), (f"{domain}-{version}-manual.zip", f"custom_components/{domain}/")]:
    with ZipFile(out / name, "w", compression=ZIP_DEFLATED) as archive:
        for path in files:
            info = ZipInfo(prefix + path.relative_to(folder).as_posix(), (2020, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    with ZipFile(out / name) as archive:
        assert archive.testzip() is None
        assert prefix + "manifest.json" in archive.namelist()
checksums = "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in sorted(out.glob("*.zip")))
(out / "SHA256SUMS.txt").write_text(checksums)
print(checksums)
if "--release" in sys.argv:
    repo = os.environ["GITHUB_REPOSITORY"]
    existing = subprocess.run(["gh", "release", "view", tag, "--repo", repo], capture_output=True)
    if existing.returncode == 0:
        # Published versions are immutable; bump the manifest for the next release.
        print(f"{tag} already exists; keeping its assets unchanged.")
        raise SystemExit(0)
    subprocess.run(["gh", "release", "create", tag, "--repo", repo, "--target", os.environ["GITHUB_SHA"],
                    "--title", f"{manifest['name']} {version}", "--generate-notes",
                    *map(str, sorted(out.iterdir()))], check=True)
