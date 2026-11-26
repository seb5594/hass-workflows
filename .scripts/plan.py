"""The job matrix of the engine's own validation: every repository it serves, from config.PROJECTS."""
import json

import config

KINDS = {"apps": "app", "integrations": "integration", "dashboards": "dashboard"}


def matrix():
    return {"include": [{"project": name, "kind": KINDS[group]}
                        for group, names in config.PROJECTS.items() for name in names]}


if __name__ == "__main__":
    print(json.dumps(matrix()))
