"""Build one declared architecture, smoke-test the image and record its metrics."""
import re
import subprocess
import sys
from pathlib import Path

import yaml

import metrics
import validate_app
from common import run, run_captured

ENTRYPOINT_SMOKE_TEST = "bash -n /entrypoint.sh /run.sh && test -x /run.sh"
# Every s6 run/finish script must parse and be executable.
S6_SMOKE_TEST = ("find /etc/s6-overlay/s6-rc.d -type f \\( -name run -o -name finish \\) "
                 "-exec bash -n {} \\; -exec test -x {} \\;")
UTILS_TEST = (
    "printf '%s' '{\"data\":{\"title\":\"CI\"}}' > /tmp/sample.json; "
    "/utils/jsonToYaml.py /tmp/sample.json data; grep -q 'title: CI' /tmp/sample.yaml; "
    "git init -q /tmp/secrets-check; cd /tmp/secrets-check; "
    "git secrets --add CI_TEST_PATTERN; git secrets --list | grep -q CI_TEST_PATTERN"
)


def image_size(image):
    output = subprocess.run(["docker", "image", "inspect", "--format", "{{.Size}}", image],
                            check=True, capture_output=True, text=True).stdout
    return int(output)


def main(app, arch, platform):
    folder = Path(app)
    config = yaml.safe_load((folder / "config.yaml").read_text())
    assert arch in config["arch"]
    image = f"local/{app}:{arch}"
    args = ["docker", "buildx", "build", "--platform", platform, "--load", "--tag", image,
            "--build-arg", f"BUILD_ARCH={arch}", "--build-arg", f"BUILD_VERSION={config['version']}"]
    build_file = folder / "build.yaml"
    if build_file.exists():
        base = yaml.safe_load(build_file.read_text())["build_from"][arch]
        args += ["--build-arg", f"BUILD_FROM={base}"]
    run(*args, app)
    run("docker", "run", "--rm", "--platform", platform, "--entrypoint", "/bin/bash", image,
        "-c", S6_SMOKE_TEST if validate_app.s6_services(folder) else ENTRYPOINT_SMOKE_TEST)
    metrics.record(f"image_size.{arch}", image_size(image))
    if arch != "amd64":
        return
    runtime = Path(".github/tests/runtime.sh")
    if runtime.exists():
        output = run_captured("docker", "run", "--rm", "--entrypoint", "/bin/bash",
                              "-v", f"{runtime.resolve()}:/runtime.sh:ro", image, "/runtime.sh")
        # Runtime scripts report every scenario as a "PASS: <name>" line.
        metrics.record("runtime_tests", len(re.findall(r"^PASS:", output, re.M)))
    if (folder / "root/utils/jsonToYaml.py").exists():
        run("docker", "run", "--rm", "--entrypoint", "/bin/bash", image, "-c", UTILS_TEST)


if __name__ == "__main__":
    main(*sys.argv[1:4])
