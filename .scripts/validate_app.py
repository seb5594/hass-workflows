"""Validate app metadata before container builds or publication."""
import re
import sys
from pathlib import Path

import yaml

from common import PLATFORMS

app = Path(sys.argv[1])
config = yaml.safe_load((app / "config.yaml").read_text())
assert config["slug"] == app.name, "App directory and slug must agree"
assert re.fullmatch(r"\d+\.\d+(?:\.\d+)?", str(config["version"])), "Use a stable numeric version"
assert "(dev)" not in config["name"], "Release app names must not contain (dev)"
assert config["arch"] and set(config["arch"]) <= set(PLATFORMS)
assert (app / "entrypoint.sh").is_file()
print(f"Validated {config['name']} {config['version']}")
