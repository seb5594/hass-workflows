"""The consistency rules every integration shares."""
import json
import struct
import tempfile
import unittest
from pathlib import Path

from support import ENGINE  # noqa: F401

import integration_checks as checks


def png(width, height):
    """The header of a PNG, which is all the size check reads."""
    return checks.PNG_SIGNATURE + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height)


class IntegrationRepository(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.component = self.root / "custom_components" / "demo"
        (self.component / "translations").mkdir(parents=True)
        self.write("manifest.json", {"domain": "demo"})
        strings = {"config": {"step": {"user": {"title": "Demo"}}}, "services": {"run": {"name": "Run", "description": "Runs.", "fields": {"speed": {"name": "Speed", "description": "How fast."}}}}}
        self.write("strings.json", strings)
        self.write("translations/en.json", strings)
        (self.component / "services.yaml").write_text("run:\n  fields:\n    speed:\n      selector:\n        number:\n")

    def write(self, name, data):
        (self.component / name).write_text(json.dumps(data))

    def found(self):
        return checks.problems(self.root)

    def test_a_consistent_integration_has_no_problems(self):
        self.assertEqual(self.found(), [])

    def test_strings_and_english_translation_must_match(self):
        self.write("translations/en.json", {"config": {}})
        self.assertTrue(any("must mirror strings.json" in problem for problem in self.found()))

    def test_other_languages_need_every_key_and_warn_about_extras(self):
        self.write("translations/de.json", {"config": {"step": {"user": {"extra": "x"}}}, "services": {}})
        found = self.found()
        self.assertTrue(any("missing key config.step.user.title" in p and not p.startswith(checks.WARNING) for p in found))
        self.assertTrue(any(p.startswith(checks.WARNING) and "config.step.user.extra" in p for p in found))

    def test_services_and_fields_must_exist_on_both_sides(self):
        (self.component / "services.yaml").write_text("run:\n  fields:\n    speed: {}\n    colour: {}\nstop: {}\n")
        found = " ".join(self.found())
        self.assertIn("service stop exists only in services.yaml", found)
        self.assertIn("field run.colour exists only in services.yaml", found)

    def test_services_need_names_and_descriptions(self):
        english = json.loads((self.component / "translations/en.json").read_text())
        english["services"]["run"]["description"] = ""
        english["services"]["run"]["fields"]["speed"]["name"] = ""
        self.write("translations/en.json", english)
        self.write("strings.json", english)
        found = " ".join(self.found())
        self.assertIn("service run has no description", found)
        self.assertIn("field run.speed has no name", found)

    def test_services_with_names_inside_services_yaml_are_left_alone(self):
        english = {"config": {}}
        self.write("translations/en.json", english)
        self.write("strings.json", english)
        self.assertEqual(self.found(), [])

    def test_zip_releases_are_named_after_the_domain(self):
        (self.root / "hacs.json").write_text(json.dumps({"zip_release": True, "filename": "other.zip"}))
        self.assertIn("filename must be demo.zip", " ".join(self.found()))
        (self.root / "hacs.json").write_text(json.dumps({"zip_release": True, "filename": "demo.zip"}))
        self.assertEqual(self.found(), [])

    def test_brand_images_follow_home_assistants_sizes(self):
        brand = self.component / "brand"
        brand.mkdir()
        for name, size in {"icon.png": (256, 256), "icon@2x.png": (512, 512), "dark_icon.png": (256, 256),
                           "logo.png": (512, 256), "logo@2x.png": (1024, 512)}.items():
            (brand / name).write_bytes(png(*size))
        self.assertEqual(self.found(), [])
        (brand / "icon.png").write_bytes(png(200, 200))
        (brand / "logo@2x.png").write_bytes(png(1024, 100))
        (brand / "dark_logo.png").write_bytes(b"not a png at all, not a png at all")
        found = " ".join(self.found())
        self.assertIn("an icon must be 256x256", found)
        self.assertIn("shorter side of a logo@2x must be 256-512", found)
        self.assertIn("is not a PNG file", found)

    def test_main_fails_only_for_errors(self):
        self.write("translations/de.json", {"config": {"step": {"user": {"title": "x", "extra": "y"}}}, "services": {"run": {"name": "x", "description": "x", "fields": {"speed": {"name": "x", "description": "x"}}}}})
        self.assertEqual(checks.main(self.root), 0)  # only a warning
        (self.component / "translations/de.json").write_text("{}")
        self.assertEqual(checks.main(self.root), 1)


if __name__ == "__main__":
    unittest.main()
