"""Validate app metadata before container builds or publication."""
import re
import sys
from pathlib import Path

import yaml

from config import PLATFORMS


def instructions(dockerfile):
    """Logical Dockerfile instructions: comments dropped, continuation lines joined."""
    pending = []
    for line in dockerfile.splitlines():
        if line.lstrip().startswith("#"):
            continue
        pending.append(line.rstrip().removesuffix("\\").strip())
        if not line.rstrip().endswith("\\"):
            yield " ".join(pending)
            pending = []


def unpinned_packages(dockerfile):
    """apk packages without an exact =version."""
    missing = []
    for instruction in instructions(dockerfile):
        for command in re.split(r"&&|;", instruction):
            words = command.split()
            if "apk" in words and "add" in words:
                packages = [w for w in words[words.index("add") + 1:] if not w.startswith("-")]
                missing += [w for w in packages if "=" not in w]
    return missing


def check_static_versions(dockerfile):
    base = re.search(r"^ARG BUILD_FROM=(\S+)", dockerfile, re.M)
    assert base, "Dockerfile must declare a default base image: ARG BUILD_FROM=<image>:<tag>"
    assert ":" in base.group(1) and not base.group(1).endswith(":latest"), "Pin the base image to a tag"
    missing = unpinned_packages(dockerfile)
    assert not missing, f"Pin apk packages to exact versions: {', '.join(missing)}"


def main(folder):
    app = Path(folder)
    config = yaml.safe_load((app / "config.yaml").read_text())
    assert config["slug"] == app.name, "App directory and slug must agree"
    assert re.fullmatch(r"\d+\.\d+(?:\.\d+)?", str(config["version"])), "Use a stable numeric version"
    assert "(dev)" not in config["name"], "Release app names must not contain (dev)"
    assert config["arch"] and set(config["arch"]) <= set(PLATFORMS)
    assert (app / "entrypoint.sh").is_file()
    check_static_versions((app / "Dockerfile").read_text())
    print(f"Validated {config['name']} {config['version']}")


if __name__ == "__main__":
    main(sys.argv[1])
