"""Build the architectures that only the previous generation of Home Assistant base images covers.

armv7, armhf and i386 stopped at base image 3.22, so their packages come from an older Alpine than
the current ones. A Dockerfile keeps both pin sets: `ARG NAME=<current>` and, next to it,
`ARG NAME_LEGACY=<older>`. Building a legacy architecture swaps the base image and hands each
legacy value to the Dockerfile as the plain one.
"""
import re

import config

SUFFIX = "_LEGACY"
ARGUMENT = re.compile(r"^\s*ARG\s+([A-Za-z0-9_]+)=(\S*)", re.M)


def is_legacy(arch):
    return arch in config.LEGACY_ARCHES


def defaults(dockerfile):
    """Every `ARG NAME=value` default of the Dockerfile."""
    return dict(ARGUMENT.findall(dockerfile))


def build_args(arch, dockerfile):
    """`--build-arg` options that turn the build for `arch` into a legacy build; none for others."""
    if not is_legacy(arch):
        return []
    values = {"BUILD_FROM": config.LEGACY_BASE.format(arch=arch)}
    values.update({name.removesuffix(SUFFIX): value
                   for name, value in defaults(dockerfile).items() if name.endswith(SUFFIX)})
    return [option for name, value in values.items() for option in ("--build-arg", f"{name}={value}")]
