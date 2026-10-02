#!/usr/bin/env python3
"""Commit, push and notify: the git steps shared by catalog, hub and README refresh.

CLI (used by the composite actions):
    gitops.py publish "commit message" [--notify hub]
Environment: TARGET_BRANCH (branch to push), GH_TOKEN (optional push credentials, otherwise the
checkout's own), NOTIFY_TOKEN (token allowed to dispatch the --notify event).
"""
import base64
import os
import subprocess
import sys

import config
import github_api

EXCLUDE_ENGINE = ["--", ".", ":!.engine"]
# --notify targets: name -> (event, repository)
NOTIFY_TARGETS = {"hub": (config.EVENTS["hub"], config.HUB_REPOSITORY)}


def git_command(token=None):
    """`git` prefix with the bot identity and, when given, authentication for github.com."""
    command = ["git", "-c", "user.name=github-actions[bot]",
               "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com"]
    if token:
        credentials = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        command[1:1] = ["-c", f"http.https://github.com/.extraheader=AUTHORIZATION: basic {credentials}"]
    return command


def commit_and_push(message, branch, token=None, paths=None):
    """Stage `paths` (default: everything except the engine checkout); False when nothing changed."""
    git = git_command(token)
    subprocess.run([*git, "add", "--all", *(["--", *paths] if paths else EXCLUDE_ENGINE)], check=True)
    if subprocess.run([*git, "diff", "--cached", "--quiet"]).returncode == 0:
        return False
    subprocess.run([*git, "commit", "-q", "-m", message], check=True)
    subprocess.run([*git, "push", "-q", "origin", f"HEAD:refs/heads/{branch}"], check=True)
    return True


def dispatch(repository, event_type, token, payload=None):
    """Send a repository_dispatch event so another repository refreshes."""
    github_api.post_json(f"https://api.github.com/repos/{repository}/dispatches",
                         {"event_type": event_type, "client_payload": payload or {}}, token)


def notify(event, repository, token):
    """Best effort: a missing token or a failed call only logs, the hourly run catches up."""
    if not token:
        print(f"No token to notify {repository}; its scheduled run picks the change up.")
        return
    try:
        dispatch(repository, event, token, {"sha": os.environ.get("GITHUB_SHA", "")})
    except RuntimeError as error:
        print(f"::warning::{repository} could not be notified: {error}")


def publish(message, notify_target=None, env=os.environ):
    branch = env["TARGET_BRANCH"]
    if not commit_and_push(message, branch, env.get("GH_TOKEN")):
        print("Nothing changed; nothing to publish.")
        return
    if notify_target:
        event, repository = NOTIFY_TARGETS[notify_target]
        notify(event, repository, env.get("NOTIFY_TOKEN"))


def main(arguments):
    if len(arguments) < 2 or arguments[0] != "publish":
        raise SystemExit(__doc__)
    target = arguments[arguments.index("--notify") + 1] if "--notify" in arguments else None
    publish(arguments[1], target)


if __name__ == "__main__":
    main(sys.argv[1:])
