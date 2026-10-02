"""Discover, validate, build and publish one app or integration."""
import json
import os
import re
import sys
import time
import tomllib
from pathlib import Path

import yaml

import metrics
import readme
from common import PLATFORMS, run, run_captured

ENGINE = Path(__file__).resolve().parents[1]
YAMLLINT_RULES = "{extends: relaxed, rules: {line-length: disable, truthy: disable}}"
CALLER_REF = re.compile(r"ref: ([0-9a-f]{40})")


def discover(root=Path(".")):
    apps = [p for p in root.glob("*/config.yaml") if not p.parts[0].startswith(".")]
    integrations = list(root.glob("custom_components/*/manifest.json"))
    if len(apps) + len(integrations) != 1:
        raise ValueError("Expected exactly one app config.yaml or integration manifest.json")
    if apps:
        return "app", apps[0].parent, yaml.safe_load(apps[0].read_text())
    return "integration", integrations[0].parent, json.loads(integrations[0].read_text())


def should_publish(env=os.environ):
    """Publish from the default branch or a version tag, never from pull requests."""
    if env.get("PUBLISH", "true") != "true" or env.get("EVENT_NAME") == "pull_request":
        return False
    ref = env.get("REF", "")
    return ref == f"refs/heads/{env.get('DEFAULT_BRANCH')}" or ref.startswith("refs/tags/v")


def check_caller_workflow(kind):
    """The caller workflow must equal the shared template for the engine commit it pins."""
    workflow = Path(".github/workflows/ci.yml")
    pinned = CALLER_REF.search(workflow.read_text())
    if not pinned:
        raise ValueError(f"{workflow} must pin hass-workflows to a commit SHA")
    template = (ENGINE / f".templates/{kind}/ci.yml.tpl").read_text()
    if workflow.read_text() != template.replace("__ENGINE_SHA__", pinned.group(1)):
        raise ValueError(f"{workflow} differs from .templates/{kind}/ci.yml.tpl")


def run_project_checks():
    """Project-specific rules live next to the project in .github/checks/*.py."""
    for check in sorted(Path(".github/checks").glob("*.py")):
        run(sys.executable, str(check))


def pycodestyle_options():
    """Options from [tool.pycodestyle] in pyproject.toml; None when the project did not opt in."""
    config = Path("pyproject.toml")
    if not config.exists():
        return None
    table = tomllib.loads(config.read_text()).get("tool", {}).get("pycodestyle")
    if table is None:
        return None
    return [f"--{key}={','.join(value) if isinstance(value, list) else value}"
            for key, value in table.items()]


def test_directory():
    return next((d for d in (Path(".github/tests"), Path("tests")) if d.is_dir()), None)


def run_integration_tests(directory):
    requirements = Path("requirements-dev.txt")
    if requirements.exists():
        run(sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
            "-r", str(requirements))
        output = run_captured(sys.executable, "-m", "pytest", "-q", str(directory))
        passed = re.search(r"(\d+) passed", output)
    else:
        output = run_captured(sys.executable, "-m", "unittest", "discover", "-s", str(directory), "-v")
        passed = re.search(r"Ran (\d+) tests?", output)
    if passed:
        metrics.record("tests", int(passed.group(1)))
    frontend = sorted(str(p) for p in directory.rglob("*.test.cjs"))
    if frontend:
        run("node", "--test", *frontend)


def validate(kind, folder):
    readme.update(check=True)
    check_caller_workflow(kind)
    run("cmp", str(ENGINE / ".templates/dependabot.yml"), ".github/dependabot.yml")
    if kind == "app":
        run(sys.executable, str(ENGINE / ".scripts/validate_app.py"), str(folder))
        run("cmp", str(ENGINE / ".templates/entrypoint.sh"), str(folder / "entrypoint.sh"))
        run("yamllint", "-d", YAMLLINT_RULES, ".github/workflows", str(folder / "config.yaml"))
        scripts = sorted(str(path) for directory in [folder, Path(".github/tests")]
                         if directory.exists() for path in directory.rglob("*.sh"))
        if scripts:
            run("shellcheck", "-x", *scripts)
        return
    run("flake8", "custom_components", "--count", "--select=E9,F63,F7,F82",
        "--show-source", "--statistics")
    if (options := pycodestyle_options()) is not None:
        run(sys.executable, "-m", "pycodestyle", *options, "custom_components")
    run(sys.executable, str(ENGINE / ".scripts/package_integration.py"), "--check")
    run_project_checks()
    if directory := test_directory():
        run_integration_tests(directory)


def main(command):
    kind, folder, metadata = discover()
    if command == "inspect":
        print(f"kind={kind}")
        print(f"directory={folder.as_posix()}")
        print(f"version={metadata['version']}")
        print(f"slug={metadata.get('slug', metadata.get('domain'))}")
        print(f"publish={str(should_publish()).lower()}")
    elif command == "validate":
        validate(kind, folder)
    elif command == "build" and kind == "app":
        started = time.monotonic()
        for arch in metadata["arch"]:
            run(sys.executable, str(ENGINE / ".scripts/build_app.py"), str(folder), arch, PLATFORMS[arch])
        metrics.record("build_seconds", int(time.monotonic() - started))
    elif command == "package" and kind == "integration":
        run(sys.executable, str(ENGINE / ".scripts/package_integration.py"))
    elif command == "release":
        script = "release_app.py" if kind == "app" else "package_integration.py"
        args = [str(folder)] if kind == "app" else ["--release"]
        run(sys.executable, str(ENGINE / ".scripts" / script), *args)
    elif command in {"render-metrics", "publish-metrics"}:
        run(sys.executable, str(ENGINE / ".scripts/metrics.py"), command.split("-")[0], kind,
            str(metadata.get("slug", "")))
    else:
        raise ValueError(f"Invalid command {command!r} for {kind}")


if __name__ == "__main__":
    main(sys.argv[1])
