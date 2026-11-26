#!/usr/bin/env python3
"""Rules every dashboard project (a Lovelace card or a theme) shares.

Run from the root of a dashboard repository; the project action does that on every build. Each rule
returns plain text problems, so one run reports everything that is wrong at once.
"""
import json
import re
import sys
from pathlib import Path

import yaml

import integration_checks
import projectmeta
from integration_checks import WARNING

# X.Y.Z, X.Y.Z.BUILD (calendar versions) or a SemVer pre-release such as 1.0.0-beta.1.
VERSION = re.compile(r"\d+\.\d+\.\d+(?:\.\d+)?(?:-[0-9A-Za-z.-]+)?")
# The keys HACS accepts in hacs.json; it rejects the file when it finds another one.
HACS_KEYS = {"name", "content_in_root", "zip_release", "filename", "country", "homeassistant",
             "persistent_directory", "render_readme", "hacs"}
MINIMUM_HOME_ASSISTANT = re.compile(r"\d{4}\.\d{1,2}\.\d+")
TRANSLATION_FOLDER = Path("src")  # holds translations/en.json and one file per further language


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def check_hacs(hacs):
    """hacs.json is what HACS reads; a card names the file it installs, a theme names nothing but itself."""
    problems = [f"hacs.json: key {key} is not allowed" for key in sorted(set(hacs) - HACS_KEYS)]
    if not hacs.get("name"):
        problems.append("hacs.json: name is required")
    filename = hacs.get("filename")
    if filename is not None and (not filename.endswith(".js") or "/" in filename):
        problems.append("hacs.json: filename must be the name of one .js file without a folder")
    if hacs.get("zip_release"):
        problems.append("hacs.json: zip_release is for packages; a card is installed as one .js release asset")
    minimum = hacs.get("homeassistant")
    if minimum is not None and not MINIMUM_HOME_ASSISTANT.fullmatch(minimum):
        problems.append(f"hacs.json: homeassistant must look like 2026.2.0, found {minimum}")
    if not hacs.get("render_readme"):
        problems.append(f"{WARNING}hacs.json: render_readme lets HACS show the README as the description")
    return problems


def check_package(package, category):
    """package.json carries the version and the repository; a card also needs the script that builds it."""
    problems = []
    if not package.get("name"):
        problems.append("package.json: name is required")
    if not VERSION.fullmatch(str(package.get("version", ""))):
        problems.append("package.json: version must be X.Y.Z or a calendar version such as 2026.11.26.1")
    if projectmeta.package_repository(package).count("/") != 1:
        problems.append("package.json: repository must point to the GitHub repository")
    if category == projectmeta.CARD and "build" not in package.get("scripts", {}):
        problems.append("package.json: a card needs a `build` script that writes dist/<filename>")
    if not package.get("private"):
        problems.append(f"{WARNING}package.json: set \"private\": true, the card is released through HACS and not npm")
    return problems


def check_themes(root):
    """A theme repository ships its themes as YAML files, each a mapping of theme names to variables."""
    files = sorted(Path(root, "themes").glob("*.yaml"))
    if not files:
        return ["themes/: a theme repository needs at least one .yaml file"]
    problems = []
    for path in files:
        content = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(content, dict) or not all(isinstance(theme, dict) for theme in content.values()):
            problems.append(f"{path}: expected a mapping of theme names to their variables")
    return problems


def problems(root="."):
    """Every problem of the dashboard in `root`."""
    project = projectmeta.discover(root)
    found = check_hacs(project.hacs) + check_package(project.metadata, project.category)
    if not Path(root, "package-lock.json").is_file():
        found.append("package-lock.json: commit it, CI installs the locked versions with `npm ci`")
    if project.category == projectmeta.THEME:
        found += check_themes(root)
    found += integration_checks.check_translations(Path(root) / TRANSLATION_FOLDER)
    found += integration_checks.check_brand(Path(root))
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
    print("Dashboard files are consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
