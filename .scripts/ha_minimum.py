#!/usr/bin/env python3
"""Keep the minimum Home Assistant version of hacs.json in step with what the tests prove.

The compatibility matrix covers the selected support range. Every target leaves a small result file
(see `record`); `raise` reads them all and writes the oldest release from which every stable
target up to the newest one passed into hacs.json, which is where HACS reads the minimum.
A failing newest stable release is a regression, not a compatibility boundary, so nothing
is changed in that case. The same goes for missing results.

CLI:
    ha_minimum.py record DIR TARGET_JSON OUTCOME   write the result of one matrix target
    ha_minimum.py raise  DIR [--expected JSON]     update hacs.json; prints the chosen minimum
"""
import argparse
import json
import sys
from pathlib import Path

from ha_matrix import version_key


def record(directory, target, outcome):
    """Store whether one matrix target passed."""
    directory.mkdir(parents=True, exist_ok=True)
    item = {"homeassistant": target["homeassistant"], "preview": bool(target.get("preview")),
            "passed": outcome == "success"}
    (directory / f"{item['homeassistant']}.json").write_text(json.dumps(item) + "\n")


def load(directory):
    return [json.loads(path.read_text()) for path in sorted(Path(directory).glob("*.json"))]


def choose_minimum(results, expected=None):
    """`Y.M.0` of the oldest stable release below which something failed, or None to keep hacs.json.

    Walks down from the newest stable release while the targets pass. Preview targets never count.
    """
    if expected is not None and {item["homeassistant"] for item in results} != set(expected):
        return None
    stable = sorted((item for item in results if not item["preview"]),
                    key=lambda item: version_key(item["homeassistant"]))
    if not stable or not stable[-1]["passed"]:
        return None
    oldest = stable[-1]
    for item in reversed(stable):
        if not item["passed"]:
            break
        oldest = item
    major, minor = version_key(oldest["homeassistant"])[:2]
    return f"{major}.{minor}.0"


def write_minimum(version, root=Path(".")):
    """Set `homeassistant` in hacs.json; returns True when the file changed."""
    path = Path(root) / "hacs.json"
    if not path.is_file():
        return False
    text = path.read_text()
    data = json.loads(text)
    if data.get("homeassistant") == version:
        return False
    data["homeassistant"] = version
    indent = "\t" if "\n\t" in text else (2 if "\n  " in text else None)
    path.write_text(json.dumps(data, indent=indent, ensure_ascii=False) + "\n")
    return True


def main(arguments):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("record")
    rec.add_argument("directory", type=Path)
    rec.add_argument("target")
    rec.add_argument("outcome")
    rai = sub.add_parser("raise")
    rai.add_argument("directory", type=Path)
    rai.add_argument("--expected", help="JSON list of the targets the matrix started")
    options = parser.parse_args(arguments)
    if options.command == "record":
        record(options.directory, json.loads(options.target), options.outcome)
        return 0
    expected = [item["homeassistant"] for item in json.loads(options.expected)] if options.expected else None
    chosen = choose_minimum(load(options.directory), expected)
    if chosen is None:
        print("Results are incomplete or the newest stable release fails: hacs.json stays as it is.", file=sys.stderr)
        return 0
    print(f"changed={'true' if write_minimum(chosen) else 'false'}\nminimum={chosen}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
