"""Validate app metadata before container builds or publication."""
import re
import json
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


def apk_add(words):
    """Packages and virtual group of one `apk add` command, given the words after `add`."""
    packages, group, group_follows = [], None, False
    for word in words:
        if group_follows:
            group, group_follows = word, False
        elif word in ("--virtual", "-t"):
            group_follows = True
        elif word.startswith("--virtual="):
            group = word.partition("=")[2]
        elif not word.startswith("-"):
            packages.append(word)
    return packages, group


def apk_installs(dockerfile):
    """(packages, build_only) per `apk add`; build_only when its virtual group is deleted again in the same instruction.

    Such a toolchain never reaches the final image, so only what stays in the image has to be pinned.
    """
    for instruction in instructions(dockerfile):
        commands = [command.split() for command in re.split(r"&&|;", instruction)]
        deleted = {word for words in commands if "apk" in words and "del" in words
                   for word in words[words.index("del") + 1:]}
        for words in commands:
            if "apk" in words and "add" in words:
                packages, group = apk_add(words[words.index("add") + 1:])
                yield packages, group in deleted


def apk_packages(dockerfile):
    """Every package named in an `apk add`, as written (`name` or `name=version`)."""
    return [package for packages, _ in apk_installs(dockerfile) for package in packages]


def unpinned_packages(dockerfile):
    """apk packages that stay in the image without an exact =version."""
    return [package for packages, build_only in apk_installs(dockerfile) if not build_only
            for package in packages if "=" not in package]


def version_variables(dockerfile):
    """Names of the build arguments that carry a package version (`pkg=${NAME}`)."""
    return [match for package in apk_packages(dockerfile) if "=" in package
            for match in re.findall(r"\$\{?([A-Za-z0-9_]+)\}?", package.split("=", 1)[1])]


def s6_services(app):
    """Service names below rootfs/etc/s6-overlay/s6-rc.d (apps that use the base image's s6-overlay)."""
    root = app / "rootfs/etc/s6-overlay/s6-rc.d"
    return sorted(p.name for p in root.iterdir() if p.is_dir() and p.name != "user") if root.is_dir() else []


ENTRYPOINT, RUN_SCRIPT, S6, NATIVE = "entrypoint", "run", "s6", "native"
# Calendar versions come in two spellings: YYYY-MM-DD[.N] (first build of a day has no suffix) and
# YYYY.MM.DD.N (every build carries its number, starting at 1).
VERSION = re.compile(r"(?:\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])(?:\.(?:[2-9]|[1-9]\d+))?|"
                     r"\d{4}\.(?:0[1-9]|1[0-2])\.(?:0[1-9]|[12]\d|3[01])(?:\.[1-9]\d*)?|"
                     r"\d+\.\d+(?:\.\d+)?(?:-[0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*)?)")


# Launchers that start something else; an ENTRYPOINT that names one of them is not a native binary.
LAUNCHERS = ("/bin/sh", "/bin/ash", "/bin/bash", "/usr/bin/env", "/init")


def native_entrypoint(dockerfile):
    """The binary that the Dockerfile's exec-form ENTRYPOINT starts directly; None for scripts and launchers."""
    for instruction in reversed(list(instructions(dockerfile))):
        match = re.fullmatch(r"ENTRYPOINT\s+(\[.*\])", instruction.strip())
        if not match:
            continue
        try:
            command = json.loads(match.group(1))
        except ValueError:
            return None
        first = command[0] if command and isinstance(command[0], str) else ""
        if first.startswith("/") and first not in LAUNCHERS and not first.endswith(".sh"):
            return first
        return None
    return None


def startup_style(app, config):
    """How the app starts: rootfs s6 services, a run.sh service (`init: false`), its own binary or an entrypoint.sh."""
    if s6_services(app):
        return S6
    if config.get("init") is False:
        return RUN_SCRIPT
    dockerfile = app / "Dockerfile"
    if not (app / "entrypoint.sh").exists() and dockerfile.is_file() and native_entrypoint(dockerfile.read_text()):
        return NATIVE
    return ENTRYPOINT


def check_startup_style(app, config):
    """Apps start in exactly one of four ways; each needs its own files and none may mix."""
    style = startup_style(app, config)
    if style == NATIVE:
        assert not (app / "run.sh").exists(), "Apps that start their binary directly do not use run.sh"
        return
    if style == ENTRYPOINT:
        assert (app / "entrypoint.sh").is_file(), \
            ("Provide entrypoint.sh or s6 services under rootfs/etc/s6-overlay, run.sh with `init: false`, "
             "or start a binary directly through ENTRYPOINT [\"/path\"]")
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


def check_base_reference(reference):
    if legacy.is_personal_base(reference):
        assert "@" not in reference, f"Use the release tag without a digest for {reference}"
        assert reference.partition(":")[2] not in ("", "latest"), f"Set an explicit base image tag for {reference}"


def check_static_versions(dockerfile, arches=(), apk_version_policy="exact"):
    base = re.search(r"^ARG BUILD_FROM=(\S+)", dockerfile, re.M)
    assert base, "Dockerfile must declare a default base image: ARG BUILD_FROM=<image>:<tag>"
    reference = base.group(1).strip("\"'")
    check_base_reference(reference)
    assert ":" in reference and not reference.endswith(":latest"), "Pin the base image to a tag"
    # Only ARG defaults before the first FROM are in scope when Docker resolves stage images.
    global_args = legacy.defaults(re.split(r"^\s*FROM\s+", dockerfile, maxsplit=1, flags=re.I | re.M)[0])
    for line in instructions(dockerfile):
        stage = re.match(r"FROM\s+(?:--platform=\S+\s+)?(\S+)", line, re.I)
        if stage:
            image = re.sub(r"\$\{(\w+)\}|\$(\w+)", lambda m: global_args.get(m[1] or m[2], m[0]).strip("\"'"),
                           stage[1])
            check_base_reference(image.strip("\"'"))
    assert apk_version_policy in ("exact", "repository"), "Unknown APK version policy"
    if apk_version_policy == "exact":
        missing = unpinned_packages(dockerfile)
        assert not missing, f"Pin apk packages to exact versions: {', '.join(missing)}"
    defaults = legacy.defaults(dockerfile)
    variables = version_variables(dockerfile)
    undefined = [name for name in variables if not defaults.get(name)]
    assert not undefined, f"Give each version argument a default: {', '.join(undefined)}"
    if any(legacy.is_legacy(arch) for arch in arches) and not legacy.is_personal_base(reference):
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
        "Use a numeric version, YYYY-MM-DD with optional .2, .3, ... suffix or YYYY.MM.DD.BUILD"
    assert "(dev)" not in config["name"], "Release app names must not contain (dev)"
    assert config["arch"] and set(config["arch"]) <= set(PLATFORMS)
    check_startup_style(app, config)
    dockerfile = (app / "Dockerfile").read_text()
    project_file = app.parent / "project.json"
    project = json.loads(project_file.read_text()) if project_file.is_file() else {}
    if base_image := project.get("base_image"):
        check_base_reference(base_image)
    check_static_versions(dockerfile, config["arch"], project.get("apk_version_policy", "exact"))
    check_release_files(app, config, dockerfile)
    check_translations(app, config)
    print(f"Validated {config['name']} {config['version']}")


if __name__ == "__main__":
    main(sys.argv[1])
