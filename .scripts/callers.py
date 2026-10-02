#!/usr/bin/env python3
"""The workflow every project, catalog and the hub keeps: rendered from one template per family.

    callers.py sync  KIND SHA [DIR]   write the caller for KIND, pinned to engine commit SHA
    callers.py check KIND [DIR]       fail when the caller differs from its template

KIND is one of CALLERS below. DIR defaults to the current directory.
"""
import re
import sys
from pathlib import Path

import config
import templating

TEMPLATES = config.ENGINE_ROOT / ".templates/callers"
PIN = re.compile(r"ref: ([0-9a-f]{40})")

# kind -> (template, target file in the repository, template values)
CALLERS = {
    "app": ("project", ".github/workflows/ci.yml",
            {"KIND": "app", "TIMEOUT": "90", "PACKAGES": "  packages: write"}),
    "integration": ("project", ".github/workflows/ci.yml",
                    {"KIND": "integration", "TIMEOUT": "30", "PACKAGES": ""}),
    "catalog-apps": ("catalog", ".github/workflows/update.yml",
                     {"KIND": "apps", "TITLE": "app", "EVENT": config.EVENTS["apps"]}),
    "catalog-integrations": ("catalog", ".github/workflows/update.yml",
                             {"KIND": "integrations", "TITLE": "integration",
                              "EVENT": config.EVENTS["integrations"]}),
    "hub": ("hub", ".github/workflows/update.yml", {"EVENT": config.EVENTS["hub"]}),
}


def render(kind, sha):
    template, _, values = CALLERS[kind]
    text = (TEMPLATES / f"{template}.yml.tpl").read_text()
    return templating.fill(text, {**values, "ENGINE_REPOSITORY": config.ENGINE_REPOSITORY,
                                  "ENGINE_SHA": sha}, templating.DUNDER, once=False)


def target(kind, directory="."):
    return Path(directory) / CALLERS[kind][1]


def pinned_sha(kind, directory="."):
    found = PIN.search(target(kind, directory).read_text())
    if not found:
        raise ValueError(f"{target(kind, directory)} must pin the engine to a commit SHA")
    return found.group(1)


def check(kind, directory="."):
    """The caller must equal the template rendered for the commit it pins."""
    workflow = target(kind, directory)
    if workflow.read_text() != render(kind, pinned_sha(kind, directory)):
        raise ValueError(f"{workflow} differs from the {CALLERS[kind][0]} caller template")


def sync(kind, sha, directory="."):
    """Write the caller; returns True when the file changed."""
    workflow = target(kind, directory)
    text = render(kind, sha)
    if workflow.exists() and workflow.read_text() == text:
        return False
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text(text)
    return True


def main(arguments):
    command, kind, *rest = arguments
    if command == "sync":
        print("updated" if sync(kind, *rest) else "unchanged")
    elif command == "check":
        check(kind, *rest)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
