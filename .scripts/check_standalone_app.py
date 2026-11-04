"""Run the common source, UI and AppArmor checks for standalone apps using sync_project.py."""
import shutil
import sys
from pathlib import Path

from common import run
from projectmeta import app_projects


def main():
    run(sys.executable, "tools/sync_project.py", "--check")
    run(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v")
    apps = app_projects()
    for app in apps:
        for script in sorted((app.folder / "app/static").glob("*.js")):
            run("node", "--check", str(script))
    if Path("tests/test_webui.cjs").is_file():
        run("node", "tests/test_webui.cjs")
    if not shutil.which("apparmor_parser"):
        run("sudo", "apt-get", "update", "-qq")
        run("sudo", "apt-get", "install", "-y", "--no-install-recommends", "apparmor")
    for app in apps:
        run("apparmor_parser", "-Q", "-T", str(app.folder / "apparmor.txt"))


if __name__ == "__main__":
    main()
