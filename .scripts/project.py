"""Discover, validate, and publish one app or integration with shared commands."""
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml


ENGINE = Path(__file__).resolve().parents[1]
PLATFORMS = {
    "amd64": "linux/amd64",
    "aarch64": "linux/arm64",
    "armv7": "linux/arm/v7",
    "armhf": "linux/arm/v6",
    "i386": "linux/386",
}


def discover(root=Path(".")):
    apps = [p for p in root.glob("*/config.yaml") if not p.parts[0].startswith(".")]
    integrations = list(root.glob("custom_components/*/manifest.json"))
    if len(apps) + len(integrations) != 1:
        raise ValueError("Expected exactly one app config.yaml or integration manifest.json")
    if apps:
        config = yaml.safe_load(apps[0].read_text())
        return "app", apps[0].parent, config
    manifest = json.loads(integrations[0].read_text())
    return "integration", integrations[0].parent, manifest


def run(*args):
    subprocess.run(args, check=True)


def main(command):
    kind, folder, metadata = discover()
    if command == "inspect":
        print(f"kind={kind}")
        print(f"directory={folder.as_posix()}")
        print(f"version={metadata['version']}")
        return
    if command == "validate":
        run(sys.executable, str(ENGINE / ".scripts/readme.py"), "--check")
        run("cmp", str(ENGINE / ".templates/dependabot.yml"), ".github/dependabot.yml")
        if kind == "app":
            run(sys.executable, str(ENGINE / ".scripts/validate_app.py"), str(folder))
            if (folder / "entrypoint.sh").exists():
                run("cmp", str(ENGINE / ".templates/entrypoint.sh"), str(folder / "entrypoint.sh"))
            run("yamllint", "-d", "{extends: relaxed, rules: {line-length: disable, truthy: disable}}",
                ".github/workflows", str(folder / "config.yaml"))
            scripts = sorted(str(path) for directory in [folder, Path(".github/tests")]
                             if directory.exists() for path in directory.rglob("*.sh"))
            if scripts:
                run("shellcheck", "-x", *scripts)
        else:
            run("flake8", "custom_components", "--count", "--select=E9,F63,F7,F82",
                "--show-source", "--statistics")
            run(sys.executable, str(ENGINE / ".scripts/package_integration.py"), "--check")
            if Path("tests").is_dir():
                run(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v")
        return
    if command == "build" and kind == "app":
        for arch in metadata["arch"]:
            run(sys.executable, str(ENGINE / ".scripts/build_app.py"), str(folder), arch, PLATFORMS[arch])
        return
    if command == "package" and kind == "integration":
        run(sys.executable, str(ENGINE / ".scripts/package_integration.py"))
        return
    if command == "release":
        if kind == "app":
            run(sys.executable, str(ENGINE / ".scripts/release_app.py"), str(folder))
        else:
            run(sys.executable, str(ENGINE / ".scripts/package_integration.py"), "--release")
        return
    raise ValueError(f"Invalid command {command!r} for {kind}")


if __name__ == "__main__":
    main(sys.argv[1])
