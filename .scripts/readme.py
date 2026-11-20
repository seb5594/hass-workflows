"""Generated parts of a project README: the header above the introduction, thanks and license at the end.

The header holds the centered display name with the logo (or icon) in one heading, and the badge rows.
Everything after it, the introduction included, is written by hand and never touched.
"""
import html
import re
import sys
from pathlib import Path

import badgekit
import brand
import licenses
import live as live_facts
import metrics
import projectmeta

START = "<!-- header:begin (generated from project metadata) -->"
END = "<!-- header:end -->"
SUPPORT_START = "<!-- support:begin (generated, shared text) -->"
SUPPORT_END = "<!-- support:end -->"
LICENSE_START = "<!-- license:begin (generated from the license file) -->"
LICENSE_END = "<!-- license:end -->"
COMPAT_WORKFLOW = Path(".github/workflows/compat.yml")

# What READMEs started with before the header existed: a hand-placed logo, the title and the old
# badge block. All of it is replaced by the header, which carries the same information.
LEGACY_PREAMBLE = re.compile(
    r'\A\s*(?:<p align="center">\s*(?:<img[^>]*>|<picture>.*?</picture>)\s*</p>\s*)?'
    r"(?:# [^\n]*\n\s*)?"
    r"(?:<!-- badges:begin.*?<!-- badges:end -->\s*)?", re.S)


def title(project):
    """Picture above the name, both in one heading: GitHub draws a rule under every h1, and one
    heading keeps it below both instead of between them."""
    name = html.escape(project.name)
    image = brand.find(project)
    picture = brand.render(project, image)
    if not picture:
        return f'<h1 align="center">{name}</h1>'
    reviewed_logo = project.root / ".github/readme-title-logo"
    if (reviewed_logo.is_file() and Path(image.light).name.startswith("logo")
            and reviewed_logo.read_text(encoding="utf-8").strip() == image.light):
        return f'<h1 align="center">\n  {picture}\n</h1>'
    return f'<h1 align="center">\n  {picture}\n  <br>\n  {name}\n</h1>'


def header(root=Path("."), live=None):
    """The generated header block of the project in `root`."""
    project = projectmeta.discover(root)
    common = {"live": live, "measured_values": metrics.load(root),
              "licensed": licenses.license_file(root) is not None}
    if project.kind == projectmeta.APP:
        rows = badgekit.app_rows(project.metadata, project.repository, **common)
    else:
        rows = badgekit.integration_rows(project.metadata, project.hacs, project.repository,
                                         compat=(root / COMPAT_WORKFLOW).exists(), **common)
    return f"{START}\n" + "\n\n".join(part for part in (title(project), badgekit.render_header(rows)) if part) + f"\n{END}"


def verify(root=Path(".")):
    """The README must contain exactly one header block; its content is refreshed by the pipeline."""
    source = (root / "README.md").read_text()
    if source.count(START) != 1 or source.count(END) != 1:
        raise ValueError("README needs exactly one generated header block; run .scripts/readme.py")


def replace_block(source, start_marker, end_marker, block):
    start, end = source.index(start_marker), source.index(end_marker) + len(end_marker)
    return source[:start] + block + source[end:]


def remove_block(source, start_marker, end_marker):
    """Cut a generated block out, together with the blank lines that separated it."""
    if start_marker not in source:
        return source
    head = source[:source.index(start_marker)].rstrip("\n")
    tail = source[source.index(end_marker) + len(end_marker):].lstrip("\n")
    return f"{head}\n\n{tail}" if tail else f"{head}\n"


def place_header(source, block):
    """Replace the header, or take over from the title and badge block READMEs used to start with."""
    if START in source:
        return replace_block(source, START, END, block)
    return block + "\n\n" + source[LEGACY_PREAMBLE.match(source).end():]


def closing_blocks(root):
    """Thanks first, license last: both always form the end of the README."""
    blocks = [f"{SUPPORT_START}\n{badgekit.support_section()}\n{SUPPORT_END}"]
    if section := licenses.project_section(root):
        blocks.append(f"{LICENSE_START}\n{section}\n{LICENSE_END}")
    return "\n\n".join(blocks)


def update(root=Path("."), live=None):
    """Write the header and the closing blocks; returns True when README.md changed."""
    readme = root / "README.md"
    source = original = readme.read_text(encoding="utf-8")
    source = place_header(source, header(root, live))
    for start_marker, end_marker in ((SUPPORT_START, SUPPORT_END), (LICENSE_START, LICENSE_END)):
        source = remove_block(source, start_marker, end_marker)
    source = source.rstrip("\n") + f"\n\n{closing_blocks(root)}\n"
    if source == original:
        return False
    readme.write_text(source, encoding="utf-8")
    return True


def current_facts(root):
    """Live repository facts for a local run; without network access every badge is kept."""
    try:
        return live_facts.fetch(projectmeta.discover(root).repository)
    except (RuntimeError, OSError) as error:
        print(f"Rendering without live facts: {error}", file=sys.stderr)
        return None


if __name__ == "__main__":
    if "--check" in sys.argv:
        verify()
    else:
        update(live=None if "--offline" in sys.argv else current_facts(Path(".")))
