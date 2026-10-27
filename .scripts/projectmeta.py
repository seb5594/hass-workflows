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


def app_projects(root=Path(".")):
    """Apps in release order; multiple apps require an explicit, exhaustive bundle manifest.

    The first app supplies the repository's README and release notes. All apps in a bundle
    share a version and repository, so one tag can never silently publish a partial release.
    """
    root = Path(root)
    apps = [p for p in root.glob("*/config.yaml") if not p.relative_to(root).parts[0].startswith(".")]
    manifest = root / ".github/apps.json"
    if manifest.exists():
        declaration = json.loads(manifest.read_text())
        names = declaration.get("apps") if isinstance(declaration, dict) else None
        if not isinstance(names, list) or not names or not all(isinstance(n, str) for n in names):
            raise ValueError(".github/apps.json must contain a nonempty apps list")
        folders = {p.parent.name: p for p in apps}
        if len(names) != len(set(names)) or set(names) != set(folders):
            raise ValueError(".github/apps.json must list every app exactly once")
        apps = [folders[name] for name in names]
    elif len(apps) != 1:
        raise ValueError("Expected exactly one app config.yaml; declare a bundle in .github/apps.json")
    projects = [Project(APP, root, p.parent, yaml.safe_load(p.read_text()), {}) for p in apps]
    if len(projects) > 1 and (len({p.version for p in projects}) != 1
                              or len({p.repository for p in projects}) != 1):
        raise ValueError("Bundled apps must share the same version and repository URL")
    if len({p.slug for p in projects}) != len(projects):
        raise ValueError("Bundled apps must have distinct slugs")
    return projects


def discover(root=Path(".")):
    """One app, an explicit app bundle, or one integration below `root`."""
    root = Path(root)
    apps = [p for p in root.glob("*/config.yaml") if not p.relative_to(root).parts[0].startswith(".")]
    integrations = list(root.glob("custom_components/*/manifest.json"))
    if (apps and integrations) or (not apps and len(integrations) != 1):
        raise ValueError("Expected exactly one app config.yaml or integration manifest.json")
    if apps:
        return app_projects(root)[0]
    hacs_file = root / "hacs.json"
    hacs = json.loads(hacs_file.read_text()) if hacs_file.exists() else {}
    return Project(INTEGRATION, root, integrations[0].parent, json.loads(integrations[0].read_text()), hacs)
