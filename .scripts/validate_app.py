"""Validate app metadata before container builds or publication."""
import re
import sys
from pathlib import Path

import yaml

import legacy
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


def apk_packages(dockerfile):
    """Every package named in an `apk add`, as written (`name` or `name=version`)."""
    packages = []
    for instruction in instructions(dockerfile):
        for command in re.split(r"&&|;", instruction):
            words = command.split()
            if "apk" in words and "add" in words:
                packages += [w for w in words[words.index("add") + 1:] if not w.startswith("-")]
    return packages


def unpinned_packages(dockerfile):
    """apk packages without an exact =version."""
    return [package for package in apk_packages(dockerfile) if "=" not in package]


def version_variables(dockerfile):
    """Names of the build arguments that carry a package version (`pkg=${NAME}`)."""
    return [match for package in apk_packages(dockerfile) if "=" in package
            for match in re.findall(r"\$\{?([A-Za-z0-9_]+)\}?", package.split("=", 1)[1])]


def s6_services(app):
    """Service names below rootfs/etc/s6-overlay/s6-rc.d (apps that use the base image's s6-overlay)."""
    root = app / "rootfs/etc/s6-overlay/s6-rc.d"
    return sorted(p.name for p in root.iterdir() if p.is_dir() and p.name != "user") if root.is_dir() else []


def check_startup_style(app, config):
    """Apps either bring their own entrypoint.sh or run as s6 services, never a mix."""
    services = s6_services(app)
    if not services:
        assert (app / "entrypoint.sh").is_file(), "Provide entrypoint.sh or s6 services under rootfs/etc/s6-overlay"
        return
    assert not (app / "entrypoint.sh").exists(), "s6 apps start through /init; remove entrypoint.sh"
    assert config.get("init") is False, "s6 apps need `init: false` in config.yaml"
    root = app / "rootfs/etc/s6-overlay/s6-rc.d"
    for name in services:
        assert (root / name / "type").is_file(), f"Service {name} needs a `type` file"
        assert (root / name / "run").is_file(), f"Service {name} needs a `run` script"
        assert (root / "user/contents.d" / name).is_file(), f"Register service {name} in user/contents.d"


def check_static_versions(dockerfile, arches=()):
    base = re.search(r"^ARG BUILD_FROM=(\S+)", dockerfile, re.M)
    assert base, "Dockerfile must declare a default base image: ARG BUILD_FROM=<image>:<tag>"
    assert ":" in base.group(1) and not base.group(1).endswith(":latest"), "Pin the base image to a tag"
    missing = unpinned_packages(dockerfile)
    assert not missing, f"Pin apk packages to exact versions: {', '.join(missing)}"
    defaults = legacy.defaults(dockerfile)
    variables = version_variables(dockerfile)
    undefined = [name for name in variables if not defaults.get(name)]
    assert not undefined, f"Give each version argument a default: {', '.join(undefined)}"
    if any(legacy.is_legacy(arch) for arch in arches):
        literal = [p for p in apk_packages(dockerfile) if not re.search(r"=\$", p)]
        assert not literal, f"Pin through ARG so legacy architectures can override: {', '.join(literal)}"
        absent = [name for name in variables if not defaults.get(name + legacy.SUFFIX)]
        assert not absent, f"Add a legacy pin for: {', '.join(name + legacy.SUFFIX for name in absent)}"


def main(folder):
    app = Path(folder)
    config = yaml.safe_load((app / "config.yaml").read_text())
    assert config["slug"] == app.name, "App directory and slug must agree"
    assert re.fullmatch(r"\d+\.\d+(?:\.\d+)?", str(config["version"])), "Use a stable numeric version"
    assert "(dev)" not in config["name"], "Release app names must not contain (dev)"
    assert config["arch"] and set(config["arch"]) <= set(PLATFORMS)
    check_startup_style(app, config)
    check_static_versions((app / "Dockerfile").read_text(), config["arch"])
    print(f"Validated {config['name']} {config['version']}")


if __name__ == "__main__":
    main(sys.argv[1])
