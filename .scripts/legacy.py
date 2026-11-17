"""Build the architectures that only the previous generation of Home Assistant base images covers.

armv7, armhf and i386 stopped at base image 3.22, so their packages come from an older Alpine than
the current ones. An app writes each apk pin once, for the current Alpine:

    # renovate: datasource=repology depName=alpine_3_24/git
    ARG GIT_VERSION=2.54.0-r0

Building a legacy architecture swaps the base image and hands the Dockerfile the exact version that
the older Alpine ships, which is looked up in its package index at build time. A pin can still be
fixed by hand with a twin, `ARG GIT_VERSION_LEGACY=2.49.1-r0`; the twin wins over the lookup.
"""
import io
import re
import tarfile
import urllib.request

import config

SUFFIX = "_LEGACY"
ARGUMENT = re.compile(r"^\s*ARG\s+([A-Za-z0-9_]+)=(\S*)", re.M)
# A pin of the current Alpine: the Renovate marker names the package, the ARG below it the version.
PIN = re.compile(r"#\s*renovate:\s*datasource=repology\s+depName=alpine_\d+_\d+/(?P<package>[\w.+-]+)[ \t]*\n"
                 r"\s*ARG\s+(?P<name>[A-Za-z0-9_]+)=", re.M)
# Alpine's name for the architecture, by Home Assistant's.
APK_ARCH = {"armv7": "armv7", "armhf": "armhf", "i386": "x86"}
REPOSITORIES = ("main", "community")
MIRROR = "https://dl-cdn.alpinelinux.org/alpine"


def is_legacy(arch):
    return arch in config.LEGACY_ARCHES


def defaults(dockerfile):
    """Every `ARG NAME=value` default of the Dockerfile."""
    return dict(ARGUMENT.findall(dockerfile))


def pinned_packages(dockerfile):
    """{ARG name: apk package} for every version argument that has a Renovate marker."""
    return {match["name"]: match["package"] for match in PIN.finditer(dockerfile)
            if not match["name"].endswith(SUFFIX)}


def alpine_release(base=config.LEGACY_BASE):
    """The Alpine release of the legacy base image, e.g. 3.22 from `...:3.22-2025.11.1`."""
    return re.search(r":(\d+\.\d+)", base)[1]


def parse_index(text):
    """{package: version} from the text of an APKINDEX."""
    versions = {}
    for block in text.split("\n\n"):
        fields = dict(line.split(":", 1) for line in block.splitlines() if len(line) > 2 and line[1] == ":")
        if "P" in fields and "V" in fields:
            versions.setdefault(fields["P"], fields["V"])
    return versions


def fetch_index(release, repository, apk_arch):
    """The APKINDEX of one Alpine repository as text."""
    url = f"{MIRROR}/v{release}/{repository}/{apk_arch}/APKINDEX.tar.gz"
    with urllib.request.urlopen(url, timeout=60) as reply:
        archive = tarfile.open(fileobj=io.BytesIO(reply.read()), mode="r:gz")
    return archive.extractfile("APKINDEX").read().decode()


def versions_for(arch, fetch=fetch_index):
    """Every package of the legacy Alpine for `arch`, with its version."""
    release = alpine_release()
    versions = {}
    for repository in REPOSITORIES:
        for package, version in parse_index(fetch(release, repository, APK_ARCH[arch])).items():
            versions.setdefault(package, version)
    return versions


def resolve(arch, dockerfile, fetch=fetch_index):
    """{ARG name: version} for the legacy build: twins first, then the lookup in the older Alpine."""
    declared = defaults(dockerfile)
    wanted = {name: package for name, package in pinned_packages(dockerfile).items()
              if not declared.get(name + SUFFIX)}
    values = {name.removesuffix(SUFFIX): value for name, value in declared.items() if name.endswith(SUFFIX)}
    if wanted:
        available = versions_for(arch, fetch)
        missing = sorted(package for package in wanted.values() if package not in available)
        assert not missing, f"Alpine {alpine_release()} has no package {', '.join(missing)} for {arch}"
        values.update({name: available[package] for name, package in wanted.items()})
    return values


def build_args(arch, dockerfile, fetch=fetch_index):
    """`--build-arg` options that turn the build for `arch` into a legacy build; none for others."""
    if not is_legacy(arch) or defaults(dockerfile).get("BUILD_FROM", "").startswith(
        "ghcr.io/seb5594/home-assistant-base"
    ):
        return []
    values = {"BUILD_FROM": config.LEGACY_BASE.format(arch=arch), **resolve(arch, dockerfile, fetch)}
    return [option for name, value in values.items() for option in ("--build-arg", f"{name}={value}")]
