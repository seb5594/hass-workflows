"""Discover, validate, build and publish one app or integration."""
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import config
import gitops
import live
import managed
import metrics
import projectmeta
import readme
from common import run, run_captured
from config import PLATFORMS

ENGINE = config.ENGINE_ROOT
YAMLLINT_RULES = "{extends: relaxed, rules: {line-length: disable, truthy: disable}}"


def should_publish(env=os.environ):
    """Publish from the default branch or a version tag, never from pull requests or templates."""
    if env.get("PUBLISH", "true") != "true" or env.get("EVENT_NAME") == "pull_request":
        return False
    if env.get("IS_TEMPLATE") == "true":
        return False
    ref = env.get("REF", "")
    return ref == f"refs/heads/{env.get('DEFAULT_BRANCH')}" or ref.startswith("refs/tags/v")


def builds_images(project, env=os.environ):
    """Apps build and push their images on pushes; the weekly schedule only refreshes the README."""
    return project.kind == projectmeta.APP and env.get("EVENT_NAME") != "schedule"


def refresh_readme(project, env=os.environ):
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
    metrics.update_snapshot(slug=project.slug if project.kind == projectmeta.APP else None, owner=owner)
    try:
        facts = live.fetch(project.repository)
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


def validate(project):
    readme.verify()
    managed.check(project.kind)
    if project.kind == projectmeta.APP:
        folder = project.folder
        run(sys.executable, str(ENGINE / ".scripts/validate_app.py"), str(folder))
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
    project = projectmeta.discover()
    if command == "inspect":
        print(f"kind={project.kind}")
        print(f"directory={project.folder.as_posix()}")
        print(f"version={project.version}")
        print(f"slug={project.slug}")
        publish, images = should_publish(), builds_images(project)
        print(f"publish={str(publish).lower()}")
        print(f"images={str(images).lower()}")
        # Integrations release (a no-op once the version exists); apps only when they built images.
        print(f"release={str(publish and (images or project.kind == projectmeta.INTEGRATION)).lower()}")
    elif command == "validate":
        validate(project)
    elif command == "build" and project.kind == projectmeta.APP:
        for arch in project.metadata["arch"]:
            run(sys.executable, str(ENGINE / ".scripts/build_app.py"), str(project.folder), arch, PLATFORMS[arch])
    elif command == "package" and project.kind == projectmeta.INTEGRATION:
        run(sys.executable, str(ENGINE / ".scripts/package_integration.py"))
    elif command == "release":
        script, args = (("release_app.py", [str(project.folder)]) if project.kind == projectmeta.APP
                        else ("package_integration.py", ["--release"]))
        run(sys.executable, str(ENGINE / ".scripts" / script), *args)
    elif command == "refresh-readme":
        refresh_readme(project)
    else:
        raise ValueError(f"Invalid command {command!r} for {project.kind}")


if __name__ == "__main__":
    try:
        main(sys.argv[1])
    except subprocess.CalledProcessError:
        sys.exit(1)  # The failing command has already been reported by common.run.
    except (ValueError, AssertionError, OSError) as error:
        # stderr: the inspect command writes its stdout into GITHUB_OUTPUT.
        print(f"::error title=project.py {sys.argv[1]}::{type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)
