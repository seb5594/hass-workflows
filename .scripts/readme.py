"""Render the badge block of a project README from its own metadata."""
import json
import sys
from pathlib import Path

import yaml

import badgekit

START = "<!-- badges:begin (generated from project metadata) -->"
END = "<!-- badges:end -->"


def repository_of(url):
    """Reduce any GitHub URL to owner/name."""
    path = url.removeprefix("https://github.com/")
    return "/".join(path.split("/")[:2])


def render(root=Path(".")):
    configs = list(root.glob("*/config.yaml"))
    manifests = list(root.glob("custom_components/*/manifest.json"))
    if len(configs) + len(manifests) != 1:
        raise ValueError("Expected exactly one app or integration metadata file")
    if configs:
        data = yaml.safe_load(configs[0].read_text())
        rows = badgekit.app_rows(data, repository_of(data["url"]), configs[0].parent)
    else:
        manifest = json.loads(manifests[0].read_text())
        hacs = json.loads((root / "hacs.json").read_text())
        rows = badgekit.integration_rows(manifest, hacs, repository_of(manifest["documentation"]))
    return f"{START}\n{badgekit.render(rows)}\n{END}"


def update(root=Path("."), check=False):
    readme = root / "README.md"
    source = readme.read_text()
    block = render(root)
    if START not in source:
        if check:
            raise ValueError("README needs a generated badge block; run .scripts/readme.py")
        # First run: place the block directly below the main heading.
        head, _, rest = source.partition("\n")
        readme.write_text(f"{head}\n\n{block}\n{rest}")
        return
    if source.count(START) != 1 or source.count(END) != 1:
        raise ValueError("README needs exactly one generated badge block")
    start, end = source.index(START), source.index(END) + len(END)
    if source[start:end] == block:
        return
    if check:
        raise ValueError("Badges differ from project metadata; regenerate via .scripts/readme.py")
    readme.write_text(source[:start] + block + source[end:])


if __name__ == "__main__":
    update(check="--check" in sys.argv)
