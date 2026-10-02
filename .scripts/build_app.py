"""Build exactly the declared architecture and test the resulting image."""
import os
import subprocess
import sys
from pathlib import Path

import yaml

app, arch, platform = sys.argv[1:]
folder = Path(app)
config = yaml.safe_load((folder / "config.yaml").read_text())
assert arch in config["arch"]
image = f"local/{app}:{arch}"
args = ["docker", "buildx", "build", "--platform", platform, "--load", "--tag", image,
        "--build-arg", f"BUILD_ARCH={arch}", "--build-arg", f"BUILD_VERSION={config['version']}"]
build_file = folder / "build.yaml"
if build_file.exists():
    args += ["--build-arg", f"BUILD_FROM={yaml.safe_load(build_file.read_text())['build_from'][arch]}"]
subprocess.run(args + [app], check=True)
subprocess.run(["docker", "run", "--rm", "--platform", platform, "--entrypoint", "/bin/bash", image,
                "-c", "bash -n /entrypoint.sh /run.sh && rsync --version && test -x /run.sh"], check=True)
if arch == "amd64":
    runtime = Path(".github/tests/runtime.sh")
    if runtime.exists():
        subprocess.run(["docker", "run", "--rm", "--entrypoint", "/bin/bash",
                        "-v", f"{runtime.resolve()}:/runtime.sh:ro", image, "/runtime.sh"], check=True)
    if (folder / "root/utils/jsonToYaml.py").exists():
        subprocess.run(["docker", "run", "--rm", "--entrypoint", "/bin/bash", image, "-c",
                        "printf '%s' '{\"data\":{\"title\":\"CI\"}}' > /tmp/sample.json; "
                        "/utils/jsonToYaml.py /tmp/sample.json data; grep -q 'title: CI' /tmp/sample.yaml; "
                        "git secrets --list >/dev/null"], check=True)
