"""Static version rules for app Dockerfiles and the two startup styles."""
import tempfile
import unittest
from pathlib import Path

from support import ENGINE  # noqa: F401

import legacy
import validate_app

GOOD = """ARG BUILD_FROM=ghcr.io/home-assistant/base:3.24-2026.08.0
FROM ${BUILD_FROM}
RUN apk add --no-cache \\
    # renovate: datasource=repology depName=alpine_3_24/git
    git=2.54.0-r0 \\
    rsync=3.5.0-r0 && echo done
"""


class StaticVersions(unittest.TestCase):
    def test_pinned_dockerfile_passes(self):
        validate_app.check_static_versions(GOOD)

    def test_unpinned_package_after_a_comment_is_found(self):
        broken = GOOD.replace("rsync=3.5.0-r0", "rsync")
        with self.assertRaisesRegex(AssertionError, "rsync"):
            validate_app.check_static_versions(broken)

    def test_floating_base_images_are_rejected(self):
        for base in ("ghcr.io/home-assistant/base", "alpine:latest"):
            with self.assertRaises(AssertionError):
                validate_app.check_static_versions(GOOD.replace("ghcr.io/home-assistant/base:3.24-2026.08.0", base))


LEGACY = """ARG BUILD_FROM=ghcr.io/home-assistant/base:3.24-2026.08.0
# renovate: datasource=repology depName=alpine_3_24/git
ARG GIT_VERSION=2.54.0-r0
# renovate: datasource=repology depName=alpine_3_22/git
ARG GIT_VERSION_LEGACY=2.49.1-r0
# renovate: datasource=repology depName=alpine_3_24/make
ARG MAKE_VERSION=4.4.1-r4
# renovate: datasource=repology depName=alpine_3_22/make
ARG MAKE_VERSION_LEGACY=4.4.1-r3

FROM ${BUILD_FROM} AS build
ARG GIT_VERSION
RUN apk add --no-cache git=${GIT_VERSION} && echo built
FROM ${BUILD_FROM}
ARG GIT_VERSION
ARG MAKE_VERSION
RUN apk add --no-cache git=${GIT_VERSION} \\
    make=${MAKE_VERSION}
"""


class VersionArguments(unittest.TestCase):
    ARCHES = ["amd64", "aarch64", "armv7"]

    def test_pins_through_arguments_pass_with_and_without_legacy_architectures(self):
        validate_app.check_static_versions(LEGACY, self.ARCHES)
        validate_app.check_static_versions(LEGACY, ["amd64"])
        self.assertEqual(validate_app.version_variables(LEGACY), ["GIT_VERSION", "GIT_VERSION", "MAKE_VERSION"])

    def test_a_version_argument_needs_a_default(self):
        with self.assertRaisesRegex(AssertionError, "default: MAKE_VERSION"):
            validate_app.check_static_versions(LEGACY.replace("ARG MAKE_VERSION=4.4.1-r4\n", ""), ["amd64"])

    def test_legacy_architectures_need_a_legacy_pin_for_every_package(self):
        with self.assertRaisesRegex(AssertionError, "MAKE_VERSION_LEGACY"):
            validate_app.check_static_versions(
                LEGACY.replace("ARG MAKE_VERSION_LEGACY=4.4.1-r3\n", ""), self.ARCHES)

    def test_legacy_architectures_cannot_use_literal_pins(self):
        with self.assertRaisesRegex(AssertionError, "git=2.54.0-r0"):
            validate_app.check_static_versions(GOOD, self.ARCHES)
        validate_app.check_static_versions(GOOD, ["amd64", "aarch64"])


class LegacyBuilds(unittest.TestCase):
    def test_current_architectures_build_as_declared(self):
        for arch in ("amd64", "aarch64"):
            self.assertEqual(legacy.build_args(arch, LEGACY), [])

    def test_legacy_architectures_swap_the_base_and_hand_over_their_pins(self):
        args = legacy.build_args("i386", LEGACY)
        options = dict(pair.split("=", 1) for pair in args[1::2])
        self.assertEqual(args[::2], ["--build-arg"] * 3)
        self.assertEqual(options, {"BUILD_FROM": "ghcr.io/home-assistant/i386-base:3.22-2025.11.1",
                                   "GIT_VERSION": "2.49.1-r0", "MAKE_VERSION": "4.4.1-r3"})

    def test_only_arguments_with_a_default_are_found(self):
        self.assertEqual(legacy.defaults("ARG A=1\nARG B\n  ARG C=x-y\nRUN echo ARG D=4\n"), {"A": "1", "C": "x-y"})


class StartupStyle(unittest.TestCase):
    def app(self, tmp, s6=True, entrypoint=False, registered=True):
        app = Path(tmp) / "demo"
        service = app / "rootfs/etc/s6-overlay/s6-rc.d/demo"
        if s6:
            service.mkdir(parents=True)
            (service / "type").write_text("longrun\n")
            (service / "run").write_text("#!/command/with-contenv bash\n")
            if registered:
                (app / "rootfs/etc/s6-overlay/s6-rc.d/user/contents.d").mkdir(parents=True)
                (app / "rootfs/etc/s6-overlay/s6-rc.d/user/contents.d/demo").write_text("")
        app.mkdir(exist_ok=True)
        if entrypoint:
            (app / "entrypoint.sh").write_text("#!/bin/bash\n")
        return app

    def test_valid_s6_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            validate_app.check_startup_style(self.app(tmp), {"init": False})

    def test_s6_app_needs_init_false_and_no_entrypoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(AssertionError, "init: false"):
                validate_app.check_startup_style(self.app(tmp), {"init": True})
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(AssertionError, "remove entrypoint.sh"):
                validate_app.check_startup_style(self.app(tmp, entrypoint=True), {"init": False})

    def test_unregistered_service_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(AssertionError, "Register service demo"):
                validate_app.check_startup_style(self.app(tmp, registered=False), {"init": False})

    def test_classic_app_needs_its_entrypoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(AssertionError, "entrypoint.sh or s6"):
                validate_app.check_startup_style(self.app(tmp, s6=False), {"init": True})
            validate_app.check_startup_style(self.app(tmp, s6=False, entrypoint=True), {"init": True})


if __name__ == "__main__":
    unittest.main()
