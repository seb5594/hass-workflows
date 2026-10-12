"""The license section at the very end of every README.

Projects get a short section that names their license and links the license file. Catalogs and
the hub list several projects with their own terms, so they get a general note instead.
"""
from pathlib import Path

import badgekit

HEADING = "## License"
# Spelling variants people actually use; the first match in the repository root wins.
FILE_NAMES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "LICENCE.md", "LICENCE.txt", "COPYING")
# (words that must all appear in the first lines, full name, short name for the badge)
KNOWN_LICENSES = (
    (("apache license", "version 2.0"), "Apache License 2.0", "Apache-2.0"),
    (("mit license",), "MIT License", "MIT"),
    # The LGPL text quotes the GPL, so it has to be recognised first.
    (("gnu lesser general public license",), "GNU Lesser General Public License", "LGPL"),
    (("gnu general public license", "version 3"), "GNU General Public License v3.0", "GPL-3.0"),
    (("gnu general public license", "version 2"), "GNU General Public License v2.0", "GPL-2.0"),
    (("mozilla public license", "2.0"), "Mozilla Public License 2.0", "MPL-2.0"),
    (("bsd 3-clause",), "BSD 3-Clause License", "BSD-3-Clause"),
    (("unlicense",), "The Unlicense", "Unlicense"),
)
COLLECTION_NOTE = (
    f"{HEADING}\n\nEvery project listed here is licensed on its own. The `LICENSE` file in each "
    "repository states which terms apply.")


def license_file(root=Path(".")):
    return next((root / name for name in FILE_NAMES if (root / name).is_file()), None)


def identify(text):
    """(full name, short name) of a license text; unknown texts fall back to their first line."""
    head = " ".join(text.lower().split()[:120])
    for words, name, short in KNOWN_LICENSES:
        if all(word in head for word in words):
            return name, short
    first = next((line.strip("# \t") for line in text.splitlines() if line.strip()), "License")
    return first, first


def project_section(root=Path(".")):
    """Section for one project, or None when the repository has no license file."""
    path = license_file(root)
    if path is None:
        return None
    name, short = identify(path.read_text(encoding="utf-8", errors="replace"))
    badge = badgekit.static("license", short, "muted", path.name)
    return f"{HEADING}\n\n{badge}\n\nPublished under the [{name}]({path.name})."
