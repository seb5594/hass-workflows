"""Static version rules for app Dockerfiles."""
import unittest

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


if __name__ == "__main__":
    unittest.main()
