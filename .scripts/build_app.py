"""Build one declared architecture, smoke-test the image and record its metrics."""
import re
import os
import shlex
import subprocess
import sys
from pathlib import Path

import yaml

import legacy
import metrics
import validate_app
from common import run, run_captured

# What proves a built image is startable, by startup style. Apps started from a run.sh service
# have no generic check; their .github/tests/runtime.sh verifies the image instead. Native apps are
# only checked for their binary, the runtime script does the rest.
SMOKE_TESTS = {
    validate_app.ENTRYPOINT: "bash -n /entrypoint.sh /run.sh && test -x /run.sh",
    # Every s6 run/finish script must parse and be executable.
    validate_app.S6: ("find /etc/s6-overlay/s6-rc.d -type f \\( -name run -o -name finish \\) "
                      "-exec bash -n {} \\; -exec test -x {} \\;"),
    validate_app.RUN_SCRIPT: None,
    validate_app.NATIVE: None,  # built by smoke_test(): the binary named in the Dockerfile must exist
}
UTILS_TEST = (
    "printf '%s' '{\"data\":{\"title\":\"CI\"}}' > /tmp/sample.json; "
    "/utils/jsonToYaml.py /tmp/sample.json data; grep -q 'title: CI' /tmp/sample.yaml; "
    "git init -q /tmp/secrets-check; cd /tmp/secrets-check; "
    "git secrets --add CI_TEST_PATTERN; git secrets --list | grep -q CI_TEST_PATTERN"
)


def smoke_test(style, dockerfile):
    """The shell command that proves a built image is startable, or None when only runtime tests can."""
    if style == validate_app.NATIVE:
        return f"test -x {shlex.quote(validate_app.native_entrypoint(dockerfile))}"
    return SMOKE_TESTS[style]


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
    args += legacy.build_args(arch, (folder / "Dockerfile").read_text())
    run(*args, app)
    style = validate_app.startup_style(folder, config)
    if command := smoke_test(style, (folder / "Dockerfile").read_text()):
        run("docker", "run", "--rm", "--platform", platform, "--entrypoint", "/bin/bash", image, "-c", command)
    prefix = os.environ.get("APP_METRICS_PREFIX", "")
    metrics.record(f"{prefix}image_size.{arch}", image_size(image))
    if arch != "amd64":
        return
    runtime = Path(".github/tests/runtime.sh")
    if runtime.exists():
        # The whole test folder is mounted too, so that a runtime script can run test files that sit next to it.
        output = run_captured("docker", "run", "--rm", "--entrypoint", "/bin/bash",
                              "-v", f"{runtime.resolve()}:/runtime.sh:ro",
                              "-v", f"{runtime.resolve().parent}:/tests:ro", image, "/runtime.sh")
        # Runtime scripts report every scenario as a "PASS: <name>" line.
        metrics.record(f"{prefix}runtime_tests", len(re.findall(r"^PASS:", output, re.M)))
    if (folder / "root/utils/jsonToYaml.py").exists():
        run("docker", "run", "--rm", "--entrypoint", "/bin/bash", image, "-c", UTILS_TEST)


if __name__ == "__main__":
    main(*sys.argv[1:4])
