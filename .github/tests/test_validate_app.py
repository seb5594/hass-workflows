"""Static version rules for app Dockerfiles and the two startup styles."""
import tempfile
import unittest
from pathlib import Path

from support import ENGINE  # noqa: F401

import common
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

    def test_a_marked_pin_needs_no_legacy_twin(self):
        validate_app.check_static_versions(LEGACY.replace("ARG MAKE_VERSION_LEGACY=4.4.1-r3\n", ""), self.ARCHES)

    def test_an_unmarked_pin_needs_a_legacy_twin(self):
        unmarked = LEGACY.replace("# renovate: datasource=repology depName=alpine_3_24/make\n", "").replace(
            "ARG MAKE_VERSION_LEGACY=4.4.1-r3\n", "")
        with self.assertRaisesRegex(AssertionError, "MAKE_VERSION_LEGACY"):
            validate_app.check_static_versions(unmarked, self.ARCHES)

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

    INDEX = {("main", "x86"): "P:git\nV:2.49.1-r0\n\nP:make\nV:4.4.1-r3\n\nP:bash\nV:5.2-r0\n",
             ("community", "x86"): "P:rsync\nV:3.4.1-r0\n"}

    def fetch(self, release, repository, apk_arch):
        self.assertEqual(release, "3.22")
        return self.INDEX[(repository, apk_arch)]

    def test_pins_of_the_current_alpine_are_found_by_their_marker(self):
        self.assertEqual(legacy.pinned_packages(LEGACY), {"GIT_VERSION": "git", "MAKE_VERSION": "make"})

    def test_the_index_of_the_older_alpine_gives_the_exact_versions(self):
        without_twins = "\n".join(line for line in LEGACY.splitlines() if "_LEGACY" not in line and "alpine_3_22" not in line)
        self.assertEqual(legacy.resolve("i386", without_twins, self.fetch), {"GIT_VERSION": "2.49.1-r0", "MAKE_VERSION": "4.4.1-r3"})

    def test_a_twin_wins_over_the_lookup(self):
        twin = LEGACY.replace("GIT_VERSION_LEGACY=2.49.1-r0", "GIT_VERSION_LEGACY=2.0-r9")
        self.assertEqual(legacy.resolve("i386", twin, self.fetch)["GIT_VERSION"], "2.0-r9")

    def test_a_package_the_older_alpine_lacks_is_reported(self):
        other = LEGACY.replace("alpine_3_24/make", "alpine_3_24/nothing").replace("ARG MAKE_VERSION_LEGACY=4.4.1-r3\n", "")
        with self.assertRaisesRegex(AssertionError, "no package nothing"):
            legacy.resolve("armv7", other.replace("x86", "armv7"), lambda r, repo, arch: self.INDEX[(repo, "x86")])

    def test_an_index_is_read_into_packages_and_versions(self):
        self.assertEqual(legacy.parse_index("C:Q1\nP:a\nV:1-r0\n\nP:b\nV:2-r1\nD:x y\n"), {"a": "1-r0", "b": "2-r1"})

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

    def test_run_script_apps_need_init_false_and_run_sh(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self.app(tmp, s6=False)
            self.assertEqual(validate_app.startup_style(app, {"init": False}), validate_app.RUN_SCRIPT)
            with self.assertRaisesRegex(AssertionError, "need a run.sh"):
                validate_app.check_startup_style(app, {"init": False})
            (app / "run.sh").write_text("#!/usr/bin/with-contenv bashio\n")
            validate_app.check_startup_style(app, {"init": False})
            (app / "entrypoint.sh").write_text("#!/bin/bash\n")
            with self.assertRaisesRegex(AssertionError, "remove entrypoint.sh"):
                validate_app.check_startup_style(app, {"init": False})

    def test_styles_are_told_apart(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(validate_app.startup_style(self.app(tmp), {"init": False}), validate_app.S6)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(validate_app.startup_style(self.app(tmp, s6=False), {"init": True}),
                             validate_app.ENTRYPOINT)


class Versions(unittest.TestCase):
    def test_calendar_versions_are_additive_and_have_unambiguous_build_numbers(self):
        for version in ("2026-10-27", "2026-10-27.2", "2026-10-27.10", "2027-01-01.123"):
            self.assertTrue(validate_app.VERSION.fullmatch(version), version)
            self.assertFalse(common.is_prerelease(version), version)
        for version in ("2026-13-27", "2026-00-01", "2026-10-00", "2026-10-32",
                        "2026-10-27.1", "2026-10-27.0", "2026-10-27.02", "2026-10-27.2."):
            self.assertFalse(validate_app.VERSION.fullmatch(version), version)

    def test_dotted_calendar_versions_always_carry_a_build_number(self):
        for version in ("2026.11.10.1", "2026.11.10.2", "2026.01.31.17"):
            self.assertTrue(validate_app.VERSION.fullmatch(version), version)
            self.assertFalse(common.is_prerelease(version), version)
        for version in ("2026.13.10.1", "2026.11.32.1", "2026.11.10.0", "2026.11.10.01", "2026.11.10."):
            self.assertFalse(validate_app.VERSION.fullmatch(version), version)

    def test_numeric_versions_with_an_optional_prerelease_suffix_are_accepted(self):
        for version in ("1.74.3", "1.18", "1.0.0-beta4", "2.0.0-beta.4", "1.0.0-rc1"):
            self.assertTrue(validate_app.VERSION.fullmatch(version), version)

    def test_other_versions_are_rejected(self):
        for version in ("v1.0.0", "1", "1.0.0-", "1.0.0 beta", "latest"):
            self.assertFalse(validate_app.VERSION.fullmatch(version), version)

    def test_prereleases_of_apps_and_integrations_are_recognised(self):
        for version in ("1.0.0-beta4", "1.0.0b1", "2.1.0rc2", "0.3.0a1"):
            self.assertTrue(common.is_prerelease(version), version)
        for version in ("1.0.0", "1.74.3"):
            self.assertFalse(common.is_prerelease(version), version)
        self.assertEqual(common.release_flags("1.0.0-beta4"), ["--prerelease"])
        self.assertEqual(common.release_flags("1.0.0"), [])


if __name__ == "__main__":
    unittest.main()


class ReleaseFiles(unittest.TestCase):
    CONFIG = {"version": "1.2.0", "schema": {"a": "str", "group": {"b": "bool?", "items": [{"c": "str"}]}}}

    def app(self, tmp, changelog="# Changelog\n\n## 1.2.0\n\n* x\n", pictures=True):
        app = Path(tmp) / "demo"
        app.mkdir()
        (app / "CHANGELOG.md").write_text(changelog)
        for name in ("icon.png", "logo.png") if pictures else ():
            (app / name).write_bytes(b"x")
        return app

    DOCKERFILE = "ARG BUILD_VERSION=1.2.0\n"

    def test_a_complete_release_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            validate_app.check_release_files(self.app(tmp), self.CONFIG, self.DOCKERFILE)

    def test_the_versions_have_to_agree(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(AssertionError, "BUILD_VERSION 1.1.0"):
            validate_app.check_release_files(self.app(tmp), self.CONFIG, "ARG BUILD_VERSION=1.1.0\n")

    def test_the_changelog_needs_an_entry_for_the_version(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(AssertionError, "no entry for 1.2.0"):
            validate_app.check_release_files(self.app(tmp, "# Changelog\n\n## 1.1.0\n"), self.CONFIG, self.DOCKERFILE)

    def test_the_pictures_are_required(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(AssertionError, "icon.png"):
            validate_app.check_release_files(self.app(tmp, pictures=False), self.CONFIG, self.DOCKERFILE)

    def test_every_option_needs_a_translated_name(self):
        english = "configuration:\n  a: {name: A}\n  group:\n    name: G\n    fields:\n      b: {name: B}\n      items: {name: I, fields: {c: {name: C}}}\n"
        with tempfile.TemporaryDirectory() as tmp:
            app = self.app(tmp)
            (app / "translations").mkdir()
            (app / "translations/en.yaml").write_text(english)
            validate_app.check_translations(app, self.CONFIG)
            (app / "translations/de.yaml").write_text(english.replace("      b: {name: B}\n", ""))
            with self.assertRaisesRegex(AssertionError, "de.yaml does not translate: group.b"):
                validate_app.check_translations(app, self.CONFIG)
