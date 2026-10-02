"""Static version rules for app Dockerfiles and the two startup styles."""
import tempfile
import unittest
from pathlib import Path

from support import ENGINE  # noqa: F401

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
