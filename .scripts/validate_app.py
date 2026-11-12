"""Validate app metadata before container builds or publication."""
import re
import sys
from pathlib import Path

import yaml

import legacy
import upstream
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


ENTRYPOINT, RUN_SCRIPT, S6 = "entrypoint", "run", "s6"
VERSION = re.compile(r"(?:\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])(?:\.(?:[2-9]|[1-9]\d+))?|"
                     r"\d+\.\d+(?:\.\d+)?(?:-[0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*)?)")


def startup_style(app, config):
    """How the app starts: its own entrypoint.sh, a run.sh service (`init: false`) or rootfs s6 services."""
    if s6_services(app):
        return S6
    return RUN_SCRIPT if config.get("init") is False else ENTRYPOINT


def check_startup_style(app, config):
    """Apps start in exactly one of three ways; each needs its own files and none may mix."""
    style = startup_style(app, config)
    if style == ENTRYPOINT:
        assert (app / "entrypoint.sh").is_file(), \
            "Provide entrypoint.sh or s6 services under rootfs/etc/s6-overlay, or run.sh with `init: false`"
        return
    assert not (app / "entrypoint.sh").exists(), "s6 apps start through /init; remove entrypoint.sh"
    assert config.get("init") is False, "s6 apps need `init: false` in config.yaml"
    if style == RUN_SCRIPT:
        assert (app / "run.sh").is_file(), "Apps with `init: false` need a run.sh service script"
        return
    root = app / "rootfs/etc/s6-overlay/s6-rc.d"
    for name in s6_services(app):
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
        resolvable = set(legacy.pinned_packages(dockerfile))
        absent = [name for name in variables
                  if name not in resolvable and not defaults.get(name + legacy.SUFFIX)]
        assert not absent, ("Mark the pin for Renovate (`# renovate: datasource=repology depName=alpine_3_24/<package>`) "
                            f"or add a legacy pin for: {', '.join(name + legacy.SUFFIX for name in absent)}")


def schema_keys(schema, path=""):
    """Dotted paths of every option in a schema; the items of a list of mappings count as one level."""
    keys = []
    for key, value in (schema or {}).items():
        keys.append(f"{path}{key}")
        if isinstance(value, list) and value and isinstance(value[0], dict):
            value = value[0]
        if isinstance(value, dict):
            keys += schema_keys(value, f"{path}{key}.")
    return keys


def translated_keys(fields, path=""):
    keys = []
    for key, value in (fields or {}).items():
        keys.append(f"{path}{key}")
        if isinstance(value, dict) and isinstance(value.get("fields"), dict):
            keys += translated_keys(value["fields"], f"{path}{key}.")
    return keys


def check_translations(app, config):
    """Every option has a name in every language the app ships."""
    folder = app / "translations"
    if not folder.is_dir():
        return
    wanted = schema_keys(config.get("schema"))
    for file in sorted(folder.glob("*.yaml")):
        configuration = (yaml.safe_load(file.read_text()) or {}).get("configuration") or {}
        missing = [key for key in wanted if key not in translated_keys(configuration)]
        assert not missing, f"{file.name} does not translate: {', '.join(missing)}"
        entries = {}

        def collect(fields, path=""):
            for key, value in (fields or {}).items():
                entries[f"{path}{key}"] = value
                if isinstance(value, dict):
                    collect(value.get("fields"), f"{path}{key}.")

        collect(configuration)
        blank = [key for key in wanted if not entries[key].get("name")]
        assert not blank, f"{file.name} needs a name for: {', '.join(blank)}"


def check_release_files(app, config, dockerfile):
    """What a release needs besides the code: the version in step everywhere, a changelog entry, the pictures."""
    version = str(config["version"])
    aligned = upstream.aligned_version(app)
    assert aligned is None or aligned == version, \
        f"App version {version} must match the primary upstream image version {aligned}"
    declared = re.search(r"^ARG BUILD_VERSION=(\S+)", dockerfile, re.M)
    assert declared, "Dockerfile must declare ARG BUILD_VERSION=<version>"
    assert declared.group(1) == version, \
        f"Dockerfile says BUILD_VERSION {declared.group(1)} but config.yaml says {version}"
    changelog = app / "CHANGELOG.md"
    assert changelog.is_file(), "Add a CHANGELOG.md"
    assert re.search(rf"^#+\s*\[?{re.escape(version)}\]?\b", changelog.read_text(), re.M), \
        f"CHANGELOG.md has no entry for {version}"
    for picture in ("icon.png", "logo.png"):
        assert (app / picture).is_file(), f"Add {picture}"


def main(folder):
    app = Path(folder)
    config = yaml.safe_load((app / "config.yaml").read_text())
    assert config["slug"] == app.name, "App directory and slug must agree"
    assert VERSION.fullmatch(str(config["version"])), \
        "Use a numeric version or YYYY-MM-DD with optional .2, .3, ... build suffix"
    assert "(dev)" not in config["name"], "Release app names must not contain (dev)"
    assert config["arch"] and set(config["arch"]) <= set(PLATFORMS)
    check_startup_style(app, config)
    dockerfile = (app / "Dockerfile").read_text()
    check_static_versions(dockerfile, config["arch"])
    check_release_files(app, config, dockerfile)
    check_translations(app, config)
    print(f"Validated {config['name']} {config['version']}")


if __name__ == "__main__":
    main(sys.argv[1])
