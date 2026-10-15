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
assert (app / "entrypoint.sh").is_file()
print(f"Validated {config['name']} {config['version']}")
