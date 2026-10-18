"""Validate app metadata before container builds or publication."""
import re
import sys
from pathlib import Path

import yaml

app = Path(sys.argv[1])
config = yaml.safe_load((app / "config.yaml").read_text())
assert config["slug"] == app.name, "App directory and slug must agree"
assert re.fullmatch(r"\d+\.\d+(?:\.\d+)?(?:-[0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*)?", str(config["version"])), "Use a numeric version, optionally with a pre-release suffix like -beta.4"
assert "(dev)" not in config["name"], "Release app names must not contain (dev)"
assert config["arch"] and set(config["arch"]) <= {"amd64", "aarch64", "armv7", "armhf", "i386"}
# Apps either bring their own entrypoint.sh or run as a service of the base image's s6-overlay.
if config.get("init") is False:
    assert not (app / "entrypoint.sh").exists(), "Apps with `init: false` start through run.sh; remove entrypoint.sh"
    assert (app / "run.sh").is_file(), "Apps with `init: false` need a run.sh service script"
else:
    assert (app / "entrypoint.sh").is_file(), "Provide entrypoint.sh, or set `init: false` and provide run.sh"
print(f"Validated {config['name']} {config['version']}")
