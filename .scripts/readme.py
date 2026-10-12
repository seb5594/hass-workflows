"""Generated parts of a project README: the badge block below the title, thanks and license at the end."""
import json
import sys
from pathlib import Path

import yaml

import badgekit
import licenses
import metrics

START = "<!-- badges:begin (generated from project metadata) -->"
END = "<!-- badges:end -->"
SUPPORT_START = "<!-- support:begin (generated, shared text) -->"
SUPPORT_END = "<!-- support:end -->"
LICENSE_START = "<!-- license:begin (generated from the license file) -->"
LICENSE_END = "<!-- license:end -->"
COMPAT_WORKFLOW = Path(".github/workflows/compat.yml")


def repository_of(url):
    """Reduce any GitHub URL to owner/name."""
    path = url.removeprefix("https://github.com/")
    return "/".join(path.split("/")[:2])


def render(root=Path("."), live=None):
    configs = list(root.glob("*/config.yaml"))
    manifests = list(root.glob("custom_components/*/manifest.json"))
    if len(configs) + len(manifests) != 1:
        raise ValueError("Expected exactly one app or integration metadata file")
    measured = metrics.load(root)
    if configs:
        data = yaml.safe_load(configs[0].read_text())
        rows = badgekit.app_rows(data, repository_of(data["url"]), configs[0].parent, live=live,
                                 measured_values=measured)
    else:
        manifest = json.loads(manifests[0].read_text())
        hacs = json.loads((root / "hacs.json").read_text())
        rows = badgekit.integration_rows(manifest, hacs, repository_of(manifest["documentation"]), live=live,
                                         measured_values=measured, compat=(root / COMPAT_WORKFLOW).exists())
    return f"{START}\n{badgekit.render(rows)}\n{END}"


def repository(root=Path(".")):
    """owner/name of the project in `root`, taken from its metadata."""
    configs = list(root.glob("*/config.yaml"))
    if configs:
        return repository_of(yaml.safe_load(configs[0].read_text())["url"])
    manifest = next(root.glob("custom_components/*/manifest.json"))
    return repository_of(json.loads(manifest.read_text())["documentation"])


def verify(root=Path(".")):
    """The README must contain exactly one badge block; its content is refreshed by the pipeline."""
    source = (root / "README.md").read_text()
    if source.count(START) != 1 or source.count(END) != 1:
        raise ValueError("README needs exactly one generated badge block; run .scripts/readme.py")


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


def closing_blocks(root):
    """Thanks first, license last: both always form the end of the README."""
    blocks = [f"{SUPPORT_START}\n{badgekit.support_section()}\n{SUPPORT_END}"]
    if section := licenses.project_section(root):
        blocks.append(f"{LICENSE_START}\n{section}\n{LICENSE_END}")
    return "\n\n".join(blocks)


def update(root=Path("."), live=None):
    """Write the badge block and the closing blocks; returns True when README.md changed."""
    readme = root / "README.md"
    source = original = readme.read_text()
    block = render(root, live)
    if START not in source:
        # First run: place the block directly below the main heading.
        head, _, rest = source.partition("\n")
        source = f"{head}\n\n{block}\n{rest}"
    else:
        verify(root)
        source = replace_block(source, START, END, block)
    for start_marker, end_marker in ((SUPPORT_START, SUPPORT_END), (LICENSE_START, LICENSE_END)):
        source = remove_block(source, start_marker, end_marker)
    source = source.rstrip("\n") + f"\n\n{closing_blocks(root)}\n"
    if source == original:
        return False
    readme.write_text(source)
    return True


if __name__ == "__main__":
    if "--check" in sys.argv:
        verify()
    else:
        update(live=None)
