"""Render the badge block of a project README from its own metadata."""
import json
import sys
from pathlib import Path

import yaml

import badgekit

START = "<!-- badges:begin (generated from project metadata) -->"
END = "<!-- badges:end -->"
SUPPORT_START = "<!-- support:begin (generated, shared text) -->"
SUPPORT_END = "<!-- support:end -->"


def repository_of(url):
    """Reduce any GitHub URL to owner/name."""
    path = url.removeprefix("https://github.com/")
    return "/".join(path.split("/")[:2])


def render(root=Path("."), live=None):
    configs = list(root.glob("*/config.yaml"))
    manifests = list(root.glob("custom_components/*/manifest.json"))
    if len(configs) + len(manifests) != 1:
        raise ValueError("Expected exactly one app or integration metadata file")
    if configs:
        data = yaml.safe_load(configs[0].read_text())
        rows = badgekit.app_rows(data, repository_of(data["url"]), configs[0].parent, live=live)
    else:
        manifest = json.loads(manifests[0].read_text())
        hacs = json.loads((root / "hacs.json").read_text())
        rows = badgekit.integration_rows(manifest, hacs, repository_of(manifest["documentation"]), live=live)
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


def update(root=Path("."), live=None):
    """Write the badge block and the shared support block; returns True when README.md changed."""
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
    support = f"{SUPPORT_START}\n{badgekit.support_section()}\n{SUPPORT_END}"
    if SUPPORT_START in source:
        source = replace_block(source, SUPPORT_START, SUPPORT_END, support)
    else:
        source = source.rstrip("\n") + f"\n\n{support}\n"
    if source == original:
        return False
    readme.write_text(source)
    return True


if __name__ == "__main__":
    if "--check" in sys.argv:
        verify()
    else:
        update(live=None)
