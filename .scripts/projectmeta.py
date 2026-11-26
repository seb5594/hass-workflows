"""The one model of a project checkout: app or integration, its folder, metadata and repository.

Every script that needs to know what it is looking at asks here instead of globbing for
`config.yaml` or `manifest.json` on its own.
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

APP, INTEGRATION, DASHBOARD = "app", "integration", "dashboard"

# A dashboard project is a HACS "Dashboard" repository: a Lovelace card (`plugin` in HACS' own
# vocabulary) or a theme. Both keep their metadata in `hacs.json` and `package.json`.
CARD, THEME = "plugin", "theme"


def repository_of(url):
    """Reduce any GitHub URL, including npm's `git+https://...git` and `github:owner/name`, to owner/name."""
    path = re.sub(r"^(?:git\+)?(?:https?://github\.com/|git@github\.com:|github:)", "", url)
    return "/".join(re.split(r"[#?]", path)[0].removesuffix(".git").split("/")[:2])


def package_repository(package):
    """The GitHub repository a package.json points to (`repository` string or object, else `homepage`)."""
    declared = package.get("repository")
    url = declared.get("url") if isinstance(declared, dict) else declared
    return repository_of(url or package.get("homepage") or "")


@dataclass(frozen=True)
class Project:
    kind: str
    root: Path
    folder: Path
    metadata: dict
    hacs: dict

    @property
    def name(self):
        """The display name; a dashboard shows the one HACS shows, its package name is only an identifier."""
        return self.hacs["name"] if self.kind == DASHBOARD else self.metadata["name"]

    @property
    def category(self):
        """HACS category of a dashboard project: `plugin` (a card) or `theme`; None for apps and integrations."""
        if self.kind != DASHBOARD:
            return None
        return CARD if self.hacs.get("filename") else THEME

    @property
    def version(self):
        return str(self.metadata["version"])

    @property
    def slug(self):
        if self.kind == APP:
            return self.metadata["slug"]
        if self.kind == DASHBOARD:
            return self.metadata["name"].rpartition("/")[2]  # drop an npm scope such as @owner/
        return self.metadata["domain"]

    @property
    def repository(self):
        """owner/name, taken from the URL the metadata itself declares."""
        if self.kind == DASHBOARD:
            return package_repository(self.metadata)
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


def dashboard_project(root):
    """A card or theme: `hacs.json` names and describes it, `package.json` carries version and repository."""
    root = Path(root)
    hacs = json.loads((root / "hacs.json").read_text())
    package = json.loads((root / "package.json").read_text())
    return Project(DASHBOARD, root, root, package, hacs)


def is_dashboard(root, apps, integrations):
    """Neither app nor integration, but the two files every HACS dashboard repository with a version has."""
    return not apps and not integrations and all((root / name).is_file() for name in ("hacs.json", "package.json"))


def discover(root=Path(".")):
    """One app, an explicit app bundle, one integration or one dashboard below `root`."""
    root = Path(root)
    apps = [p for p in root.glob("*/config.yaml") if not p.relative_to(root).parts[0].startswith(".")]
    integrations = list(root.glob("custom_components/*/manifest.json"))
    if is_dashboard(root, apps, integrations):
        return dashboard_project(root)
    if (apps and integrations) or (not apps and len(integrations) != 1):
        raise ValueError("Expected exactly one app config.yaml, integration manifest.json or dashboard hacs.json with package.json")
    if apps:
        return app_projects(root)[0]
    hacs_file = root / "hacs.json"
    hacs = json.loads(hacs_file.read_text()) if hacs_file.exists() else {}
    return Project(INTEGRATION, root, integrations[0].parent, json.loads(integrations[0].read_text()), hacs)
