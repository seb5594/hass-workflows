#!/usr/bin/env python3
"""Calendar versions of integrations: YYYY.MM.DD for the first build of a day, then .1, .2, ...

    calver.py next [VERSION]   print the version that follows VERSION (default: today's first)
    calver.py bump [DIR]       raise the version in every custom_components/*/manifest.json of DIR
                               (and in the package.json of a dashboard project)

The first build of a day carries no suffix, the second one .1, the third .2. A new day starts again
without a suffix, and the version never moves backwards. Versions of another shape (1.2.3, 1.0.0b1)
are left alone.
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

CALENDAR = re.compile(r"(\d{4})\.(\d{1,2})\.(\d{1,2})(?:\.(\d+))?")


def today():
    return datetime.now(ZoneInfo("Europe/Berlin")).date().isoformat().replace("-", ".")


def is_calendar(version):
    return CALENDAR.fullmatch(version) is not None


def next_version(version=None, day=None):
    """The version after `version` on `day` (YYYY.MM.DD, default: today in Europe/Berlin)."""
    day = day or today()
    found = CALENDAR.fullmatch(version) if version else None
    if not found:
        if version:
            raise ValueError(f"'{version}' is not a calendar version (YYYY.MM.DD[.BUILD])")
        return day
    published = ".".join(f"{int(part):02d}" for part in found.groups()[:3])
    if day > published:
        return day
    # A suffix-less version counts as build 0, so its successor is .1.
    return f"{published}.{int(found[4] or 0) + 1}"


def bump(root=Path("."), day=None):
    """Raise calendar versions in integration manifests, app config files and dashboard package.json."""
    import yaml

    root = Path(root)
    paths = sorted(root.glob("custom_components/*/manifest.json"))
    if (root / "hacs.json").is_file() and (root / "package.json").is_file() and not paths:
        paths.append(root / "package.json")
    paths += sorted(path for path in root.glob("*/config.yaml") if not path.parts[-2].startswith("."))
    changed = {}
    for path in paths:
        text = path.read_text()
        metadata = json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)
        version = str(metadata.get("version", "")).replace("-", ".")
        if not is_calendar(version):
            continue
        new = next_version(version, day)
        if path.suffix == ".json":
            updated = re.sub(r'("version"\s*:\s*)"[^"]*"', rf'\g<1>"{new}"', text, count=1)
        else:
            updated = re.sub(r'(?m)^(version:\s*)[^\n]+', rf'\g<1>"{new}"', text, count=1)
        path.write_text(updated)
        changed[str(path)] = new
    return changed


def main(arguments):
    command, *rest = arguments or [""]
    if command == "next":
        print(next_version(*rest[:1]))
    elif command == "bump":
        for path, version in bump(*rest[:1]).items():
            print(f"{path}: {version}")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
