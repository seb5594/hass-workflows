"""Render compact project badges from actual app and integration metadata."""
import json
import re
import sys
from pathlib import Path
from string import Template
from urllib.parse import quote

import yaml


ROOT = Path(__file__).resolve().parents[1]
START = "<!-- badges:begin (generated from project metadata) -->"
END = "<!-- badges:end -->"


def badge(label, value, color="157F71"):
    label = quote(label, safe="")
    value = quote(value, safe="")
    return f"![{label}](https://img.shields.io/badge/{label}-{value}-{color}?style=flat-square)"


def project(root=Path(".")):
    configs = list(root.glob("*/config.yaml"))
    manifests = list(root.glob("custom_components/*/manifest.json"))
    if len(configs) + len(manifests) != 1:
        raise ValueError("Expected exactly one app or integration metadata file")
    if configs:
        data = yaml.safe_load(configs[0].read_text())
        repository = data["url"].rstrip("/")
        kind = "app"
    else:
        data = json.loads(manifests[0].read_text())
        repository = data["documentation"].split("/blob/")[0].split("/tree/")[0].rstrip("/")
        kind = "integration"
    owner, name = repository.removeprefix("https://github.com/").split("/")[:2]
    if kind == "app":
        architectures = " ".join(badge(a, "supported") for a in data["arch"])
        maps = [entry.split(":", 1)[0] if isinstance(entry, str)
                else entry.get("type", next(iter(entry)))
                for entry in data.get("map", [])]
        readable = {"all_addon_configs": "app configs", "addons": "local apps",
                    "config": "config", "share": "share", "media": "media", "backup": "backup",
                    "ssl": "ssl"}
        capabilities = [badge("stage", data.get("stage", "stable"), "2F855A")]
        capabilities += [badge("mount", readable[m]) for m in dict.fromkeys(maps) if m in readable]
        if data.get("devices"):
            capabilities.append(badge("mount", "local disks"))
        if data.get("ingress"):
            capabilities.append(badge("ingress", "enabled", "7C3AED"))
        path = ROOT / ".templates/app/badges.md.tpl"
    else:
        architectures = ""
        capabilities = []
        path = ROOT / ".templates/integration/badges.md.tpl"
    block = Template(path.read_text()).substitute(
        VERSION=str(data["version"]), REPO=repository, OWNER=owner, NAME=name,
        ARCH_BADGES=architectures, CAPABILITY_BADGES=" ".join(capabilities))
    # Replaces removal of every empty line: retain one visual break per badge group.
    grouped = re.sub(r"\n{3,}", "\n\n", block.strip())
    return START + "\n" + grouped + "\n" + END


def update(root=Path("."), check=False):
    readme = root / "README.md"
    source = readme.read_text()
    if source.count(START) != 1 or source.count(END) != 1:
        raise ValueError("README needs exactly one generated badge block")
    start, end = source.index(START), source.index(END) + len(END)
    current, expected = source[start:end], project(root)
    if check and current != expected:
        raise ValueError("Badges differ from project metadata; regenerate via .scripts/readme.py")
    if not check and current != expected:
        readme.write_text(source[:start] + expected + source[end:])


if __name__ == "__main__":
    update(check="--check" in sys.argv)
