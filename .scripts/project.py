"""Discover, validate, build and publish one app or integration."""
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import yaml

import callers
import config
import gitops
import live
import metrics
import readme
from common import run, run_captured
from config import PLATFORMS

ENGINE = config.ENGINE_ROOT
YAMLLINT_RULES = "{extends: relaxed, rules: {line-length: disable, truthy: disable}}"


def discover(root=Path(".")):
    apps = [p for p in root.glob("*/config.yaml") if not p.parts[0].startswith(".")]
    integrations = list(root.glob("custom_components/*/manifest.json"))
    if len(apps) + len(integrations) != 1:
        raise ValueError("Expected exactly one app config.yaml or integration manifest.json")
    if apps:
        return "app", apps[0].parent, yaml.safe_load(apps[0].read_text())
    return "integration", integrations[0].parent, json.loads(integrations[0].read_text())


def should_publish(env=os.environ):
    """Publish from the default branch or a version tag, never from pull requests or templates."""
    if env.get("PUBLISH", "true") != "true" or env.get("EVENT_NAME") == "pull_request":
        return False
    if env.get("IS_TEMPLATE") == "true":
        return False
    ref = env.get("REF", "")
    return ref == f"refs/heads/{env.get('DEFAULT_BRANCH')}" or ref.startswith("refs/tags/v")


def refresh_readme(kind, metadata, env=os.environ):
    """Store this run's measurements, rewrite the README badges with live values and push both.

    Badges without a value (no releases yet, zero stars, nothing measured) are left out, so the
    block depends on live data and is regenerated here instead of being compared in CI.
    Pushes by GITHUB_TOKEN do not start another workflow run.
    """
    branch = env.get("DEFAULT_BRANCH")
    if env.get("REF") != f"refs/heads/{branch}":
        print("README badges are refreshed from the default branch only.")
        return
    owner = env.get("GITHUB_REPOSITORY", "").partition("/")[0]
    metrics.update_snapshot(slug=metadata.get("slug") if kind == "app" else None, owner=owner)
    try:
        facts = live.fetch(readme.repository())
        readme.update(live=facts)
    except RuntimeError as error:
        print(f"::warning::README badges were not refreshed: {error}")
        return
    paths = [str(path) for path in (Path("README.md"), metrics.SNAPSHOT) if path.exists()]
    try:
        changed = gitops.commit_and_push("docs: refresh README badges", branch, env["GH_TOKEN"], paths=paths)
    except subprocess.CalledProcessError:
        print("::warning::The README refresh could not be pushed; the next run will retry.")
        return
    print("README badges refreshed." if changed else "README badges are up to date.")


def shell_scripts(directories):
    """Shell files by extension or shebang, so extensionless s6 `run` and `finish` scripts are linted too."""
    found = []
    for directory in directories:
        for path in sorted(directory.rglob("*")) if directory.exists() else []:
            if not path.is_file() or path.is_symlink():
                continue
            with path.open("rb") as handle:
                first = handle.readline(200)
            if path.suffix == ".sh" or (first.startswith(b"#!") and (b"sh" in first or b"bash" in first)):
                found.append(str(path))
    return found


def run_project_checks():
    """Project-specific rules live next to the project in .github/checks/*.py."""
    for check in sorted(Path(".github/checks").glob("*.py")):
        run(sys.executable, str(check))


def dev_file(name):
    """Tooling files live in .github/dev to keep the repository root clean; the root also works."""
    return next((p for p in (Path(".github/dev") / name, Path(name)) if p.exists()), None)


def pycodestyle_options():
    """Options from [tool.pycodestyle] in pyproject.toml; None when the project did not opt in."""
    config = dev_file("pyproject.toml")
    if config is None:
        return None
    table = tomllib.loads(config.read_text()).get("tool", {}).get("pycodestyle")
    if table is None:
        return None
    return [f"--{key}={','.join(value) if isinstance(value, list) else value}"
            for key, value in table.items()]


def test_directory():
    return next((d for d in (Path(".github/tests"), Path("tests")) if d.is_dir()), None)


def run_integration_tests(directory):
    requirements, config = dev_file("requirements-dev.txt"), dev_file("pyproject.toml")
    if requirements:
        run(sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
            "-r", str(requirements))
        # An explicit config keeps pytest's paths relative to the repository root.
        options = ["-c", str(config), "--rootdir", "."] if config else []
        output = run_captured(sys.executable, "-m", "pytest", *options, "-q", str(directory))
        passed = re.search(r"(\d+) passed", output)
    else:
        output = run_captured(sys.executable, "-m", "unittest", "discover", "-s", str(directory), "-v")
        passed = re.search(r"Ran (\d+) tests?", output)
    if passed:
        metrics.record("tests", int(passed.group(1)))
    frontend = sorted(str(p) for p in directory.rglob("*.test.cjs"))
    if frontend:
        run("node", "--test", *frontend)


def check_callers(kind):
    """Integrations with tests against real Home Assistant also keep the compatibility caller."""
    callers.check(kind)
    if kind == "integration" and Path(".github/ha_tests").is_dir():
        callers.check("compat")


def validate(kind, folder):
    readme.verify()
    check_callers(kind)
    run("cmp", str(ENGINE / ".templates/dependabot.yml"), ".github/dependabot.yml")
    if Path(".github/renovate.json").exists():
        run("cmp", str(ENGINE / ".templates/renovate/renovate.json"), ".github/renovate.json")
    if kind == "app":
        run(sys.executable, str(ENGINE / ".scripts/validate_app.py"), str(folder))
        if (folder / "entrypoint.sh").exists():
            run("cmp", str(ENGINE / ".templates/entrypoint.sh"), str(folder / "entrypoint.sh"))
        run("yamllint", "-d", YAMLLINT_RULES, ".github/workflows", str(folder / "config.yaml"))
        if scripts := shell_scripts([folder, Path(".github/tests")]):
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
        for arch in metadata["arch"]:
            run(sys.executable, str(ENGINE / ".scripts/build_app.py"), str(folder), arch, PLATFORMS[arch])
    elif command == "package" and kind == "integration":
        run(sys.executable, str(ENGINE / ".scripts/package_integration.py"))
    elif command == "release":
        script = "release_app.py" if kind == "app" else "package_integration.py"
        args = [str(folder)] if kind == "app" else ["--release"]
        run(sys.executable, str(ENGINE / ".scripts" / script), *args)
    elif command == "refresh-readme":
        refresh_readme(kind, metadata)
    else:
        raise ValueError(f"Invalid command {command!r} for {kind}")


if __name__ == "__main__":
    try:
        main(sys.argv[1])
    except subprocess.CalledProcessError:
        sys.exit(1)  # The failing command has already been reported by common.run.
    except (ValueError, AssertionError, OSError) as error:
        print(f"::error title=project.py {sys.argv[1]}::{type(error).__name__}: {error}", flush=True)
        sys.exit(1)
