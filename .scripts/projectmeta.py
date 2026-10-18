"""The one model of a project checkout: app or integration, its folder, metadata and repository.

Every script that needs to know what it is looking at asks here instead of globbing for
`config.yaml` or `manifest.json` on its own.
"""
import json
from dataclasses import dataclass
from pathlib import Path

import yaml

APP, INTEGRATION = "app", "integration"


def repository_of(url):
    """Reduce any GitHub URL to owner/name."""
    path = url.removeprefix("https://github.com/")
    return "/".join(path.split("/")[:2])


@dataclass(frozen=True)
class Project:
    kind: str
    root: Path
    folder: Path
    metadata: dict
    hacs: dict

    @property
    def name(self):
        return self.metadata["name"]

    @property
    def version(self):
        return str(self.metadata["version"])

    @property
    def slug(self):
        return self.metadata["slug"] if self.kind == APP else self.metadata["domain"]

    @property
    def repository(self):
        """owner/name, taken from the URL the metadata itself declares."""
        url = self.metadata["url"] if self.kind == APP else self.metadata["documentation"]
        return repository_of(url)

    @property
    def readme(self):
        return self.root / "README.md"


def discover(root=Path(".")):
    """The single app or integration below `root`; anything else is an error."""
    root = Path(root)
    apps = [p for p in root.glob("*/config.yaml") if not p.relative_to(root).parts[0].startswith(".")]
    integrations = list(root.glob("custom_components/*/manifest.json"))
    if len(apps) + len(integrations) != 1:
        raise ValueError("Expected exactly one app config.yaml or integration manifest.json")
    if apps:
        return Project(APP, root, apps[0].parent, yaml.safe_load(apps[0].read_text()), {})
    hacs_file = root / "hacs.json"
    hacs = json.loads(hacs_file.read_text()) if hacs_file.exists() else {}
    return Project(INTEGRATION, root, integrations[0].parent, json.loads(integrations[0].read_text()), hacs)
