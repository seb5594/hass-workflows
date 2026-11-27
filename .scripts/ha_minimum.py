#!/usr/bin/env python3
"""Keep the minimum Home Assistant version of hacs.json in step with what the tests prove.

The compatibility matrix covers the selected support range. Every target leaves a small result file
(see `record`); `raise` reads them all and writes the oldest release from which every stable
target up to the newest one passed into hacs.json, which is where HACS reads the minimum.
A failing newest stable release is a regression, not a compatibility boundary, so nothing
is changed in that case. The same goes for missing results.

CLI:
    ha_minimum.py record DIR TARGET_JSON OUTCOME   write the result of one matrix target
    ha_minimum.py raise  DIR [--expected JSON] [--refine]
                                                   update hacs.json; prints the chosen minimum,
                                                   --refine bisects the gap below it first
    ha_minimum.py gate   TARGET_JSON OUTCOME       fail only when a target the project claims fails
"""
import argparse
from itertools import combinations
import json
import subprocess
import sys
from pathlib import Path

from ha_matrix import minimum_from_hacs, version_key


def record(directory, target, outcome):
    """Store whether one matrix target passed."""
    directory.mkdir(parents=True, exist_ok=True)
    item = {"homeassistant": target["homeassistant"], "preview": bool(target.get("preview")),
            "passed": {"success": True, "failure": False}.get(outcome)}
    (directory / f"{item['homeassistant']}.json").write_text(json.dumps(item) + "\n")


def load(directory):
    return [json.loads(path.read_text()) for path in sorted(Path(directory).glob("*.json"))]


def choose_minimum(results, expected=None):
    """Exact oldest patch in the passing suffix, or None when results are inconclusive.

    Walks down from the newest stable release while the targets pass. Preview targets never count.
    """
    if expected is not None and {item["homeassistant"] for item in results} != set(expected):
        return None
    stable = sorted((item for item in results if not item["preview"]),
                    key=lambda item: version_key(item["homeassistant"]))
    if not stable or any(item["passed"] is None for item in stable) or not stable[-1]["passed"]:
        return None
    oldest = stable[-1]
    for item in reversed(stable):
        if not item["passed"]:
            break
        oldest = item
    return oldest["homeassistant"]


def boundary(results):
    """(highest failed, lowest passed) stable release around the minimum, or None without a failure."""
    stable = sorted((item for item in results if not item["preview"]),
                    key=lambda item: version_key(item["homeassistant"]))
    if not stable or any(item["passed"] is None for item in stable) or not stable[-1]["passed"]:
        return None
    start = len(stable) - 1
    while start > 0 and stable[start - 1]["passed"]:
        start -= 1
    if start == 0:
        return None
    return stable[start - 1]["homeassistant"], stable[start]["homeassistant"]


def keep_declared(pair, declared):
    """Whether the declared minimum already lies in the gap the matrix could not resolve.

    Without a boundary search the coarse result would round the minimum up to the passing release,
    undoing an earlier search. A declared value inside the gap stays; the next push re-checks it.
    """
    if not pair or not declared:
        return False
    failed, passed = pair
    return version_key(failed) < version_key(declared) <= version_key(passed)


def pin_variants(target):
    """The target with every subset of its pins, the full set first and none last."""
    pins = target.get("pins", [])
    variants = []
    for size in range(len(pins), -1, -1):
        for chosen in combinations(pins, size):
            variants.append({**{k: v for k, v in target.items() if k != "pins"}, **({"pins": list(chosen)} if chosen else {})})
    return variants


def refined_minimum(failed, passed):
    """Bisect the stable patches between the failed and the passed release with real test runs.

    Returns the lowest passing release; when no patch in the gap passes, the passed release itself.
    """
    import ha_matrix
    import ha_refine

    domains, requirements = ha_matrix.manifest_dependencies(), ha_matrix.manifest_requirements()

    def passes(target):
        """True or False for a tested release; None when its environment cannot be built at all."""
        # The pins of the curated release below were made for that series; a later one may not take
        # all of them, so the largest set of them that installs is used.
        for attempt in pin_variants(target):
            try:
                results = ha_matrix.test_release(attempt, domains, requirements)
                if not results:
                    return None
                outcome = all(results.values())
            except subprocess.CalledProcessError:
                continue
            print(f"Boundary search: Home Assistant {target['homeassistant']} "
                  f"{'passes' if outcome else 'fails'}", file=sys.stderr)
            return outcome
        print(f"Boundary search: Home Assistant {target['homeassistant']} cannot be installed, skipped",
              file=sys.stderr)
        return None

    return ha_refine.refine(failed, passed, passes)


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


def gate(target, outcome, root=Path(".")):
    """Exit code of one target: a failure below the declared minimum is a known boundary, not an error."""
    if outcome == "success":
        return 0
    declared = minimum_from_hacs(root)
    if outcome == "failure" and declared and version_key(target["homeassistant"]) < version_key(declared):
        print(f"::notice::Home Assistant {target['homeassistant']} fails, which hacs.json already "
              f"excludes (minimum {declared}).")
        return 0
    return 1


def main(arguments):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("record")
    rec.add_argument("directory", type=Path)
    rec.add_argument("target")
    rec.add_argument("outcome")
    gat = sub.add_parser("gate")
    gat.add_argument("target")
    gat.add_argument("outcome")
    rai = sub.add_parser("raise")
    rai.add_argument("directory", type=Path)
    rai.add_argument("--expected", help="JSON list of the targets the matrix started")
    rai.add_argument("--refine", action="store_true",
                     help="test the stable patches between the failed and the passed release")
    options = parser.parse_args(arguments)
    if options.command == "record":
        record(options.directory, json.loads(options.target), options.outcome)
        return 0
    if options.command == "gate":
        return gate(json.loads(options.target), options.outcome)
    expected = [item["homeassistant"] for item in json.loads(options.expected)] if options.expected else None
    results = load(options.directory)
    chosen = choose_minimum(results, expected)
    pair = boundary(results)
    if chosen is not None and options.refine and pair:
        chosen = refined_minimum(*pair) or chosen
    elif chosen is not None and keep_declared(pair, minimum_from_hacs()):
        chosen = minimum_from_hacs()
    if chosen is None:
        print("Results are incomplete or the newest stable release fails: hacs.json stays as it is.", file=sys.stderr)
        return 0
    print(f"changed={'true' if write_minimum(chosen) else 'false'}\nminimum={chosen}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
