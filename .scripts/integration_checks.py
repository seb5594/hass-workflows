#!/usr/bin/env python3
"""Rules every integration shares: files that must mirror each other, and brand image sizes.

Run from the root of an integration repository; the project action does that on every build.
Each rule returns plain text problems, so one run reports everything that is wrong at once.
"""
import json
import struct
import sys
from pathlib import Path

import yaml

WARNING = "warning: "  # a problem with this prefix is reported but does not fail the build
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# Home Assistant's brand rules: icons are square, logos need a shorter side in this range (1x / 2x).
ICON_SIZE = {"": 256, "@2x": 512}
LOGO_SHORT_SIDE = {"": (128, 256), "@2x": (256, 512)}


def components(root):
    """The integration folders of the repository."""
    return sorted(path.parent for path in Path(root, "custom_components").glob("*/manifest.json"))


def flatten(tree, prefix=""):
    """All key paths of a nested dict, without the texts."""
    for key, value in tree.items():
        path = f"{prefix}{key}"
        yield path
        if isinstance(value, dict):
            yield from flatten(value, f"{path}.")


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def check_translations(component):
    """strings.json is the source of translations/en.json; every other language has the same keys."""
    problems = []
    folder = component / "translations"
    strings, english = component / "strings.json", folder / "en.json"
    if strings.is_file() and english.is_file() and load_json(strings) != load_json(english):
        problems.append(f"{strings} and {english} differ; translations/en.json must mirror strings.json")
    if not english.is_file():
        return problems
    expected = set(flatten(load_json(english)))
    for other in sorted(folder.glob("*.json")):
        if other == english:
            continue
        found = set(flatten(load_json(other)))
        for key in sorted(expected - found):
            problems.append(f"{other}: missing key {key}")
        for key in sorted(found - expected):
            problems.append(f"{WARNING}{other}: key {key} does not exist in en.json")
    return problems


def check_services(component):
    """Every service and field of services.yaml is named and described in the English translation."""
    services_file, english = component / "services.yaml", component / "translations" / "en.json"
    if not services_file.is_file() or not english.is_file():
        return []
    texts = load_json(english).get("services")
    if texts is None:  # names and descriptions still live in services.yaml
        return []
    problems = []
    services = yaml.safe_load(services_file.read_text(encoding="utf-8")) or {}
    for name in sorted(set(services) ^ set(texts)):
        where = "services.yaml" if name in services else "translations/en.json"
        problems.append(f"service {name} exists only in {where}")
    for name in sorted(set(services) & set(texts)):
        entry = texts[name]
        for key in ("name", "description"):
            if not entry.get(key):
                problems.append(f"service {name} has no {key} in translations/en.json")
        fields, described = set((services[name] or {}).get("fields", {})), entry.get("fields", {})
        for field in sorted(fields ^ set(described)):
            where = "services.yaml" if field in fields else "translations/en.json"
            problems.append(f"field {name}.{field} exists only in {where}")
        for field, field_texts in described.items():
            for key in ("name", "description"):
                if not field_texts.get(key):
                    problems.append(f"field {name}.{field} has no {key} in translations/en.json")
    return problems


def check_hacs(root, component):
    """A ZIP release is named after the integration's domain, which is what HACS downloads."""
    hacs = Path(root, "hacs.json")
    if not hacs.is_file():
        return []
    data = load_json(hacs)
    expected = f"{component.name}.zip"
    if data.get("zip_release") and data.get("filename") != expected:
        return [f"hacs.json: filename must be {expected} for zip_release, found {data.get('filename')}"]
    return []


def png_size(path):
    header = path.read_bytes()[:24]
    if header[:8] != PNG_SIGNATURE:
        raise ValueError(f"{path} is not a PNG file")
    return struct.unpack(">II", header[16:24])


def check_brand(component):
    """Icons are 256 and 512 pixels square; logos have a shorter side of 128-256 and 256-512."""
    folder = component / "brand"
    problems = []
    for path in sorted(folder.glob("*.png")) if folder.is_dir() else []:
        stem = path.stem.removeprefix("dark_")
        scale = "@2x" if stem.endswith("@2x") else ""
        kind = stem.removesuffix("@2x")
        try:
            width, height = png_size(path)
        except ValueError as error:
            problems.append(str(error))
            continue
        if kind == "icon" and (width, height) != (ICON_SIZE[scale],) * 2:
            problems.append(f"{path}: an icon{scale} must be {ICON_SIZE[scale]}x{ICON_SIZE[scale]}, found {width}x{height}")
        elif kind == "logo":
            low, high = LOGO_SHORT_SIDE[scale]
            if not low <= min(width, height) <= high:
                problems.append(f"{path}: the shorter side of a logo{scale} must be {low}-{high}, found {width}x{height}")
    return problems


def problems(root="."):
    """Every problem of every integration in the repository."""
    found = []
    for component in components(root):
        found += check_translations(component)
        found += check_services(component)
        found += check_hacs(root, component)
        found += check_brand(component)
    return found


def main(root="."):
    found = problems(root)
    errors = [problem for problem in found if not problem.startswith(WARNING)]
    for problem in found:
        if problem.startswith(WARNING):
            print(f"::warning::{problem.removeprefix(WARNING)}")
        else:
            print(f"::error::{problem}")
    if errors:
        print(f"{len(errors)} consistency problem(s) found", file=sys.stderr)
        return 1
    print("Integration files are consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
