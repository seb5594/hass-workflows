"""Prepare or submit one integration to the upstream Marketplace catalog."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import quote

UPSTREAM = "hacs/default"
# Identifies the pull request template of UPSTREAM; its bot checks for it.
TEMPLATE_ID = "73253df5-5376-4e68-8c16-b234da6a2de3"


def api(path, payload=None, method="POST"):
    command = ["gh", "api", path]
    if payload is not None:
        command += ["--method", method, "--input", "-"]
    result = subprocess.run(command, input=json.dumps(payload) if payload is not None else None,
                            capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"GitHub API request failed for {path}: {result.stderr.strip()}")
    return json.loads(result.stdout)


def latest_release(repository):
    """The newest stable release, or None: drafts and pre-releases never count."""
    try:
        return api(f"repos/{repository}/releases/latest")
    except subprocess.CalledProcessError:
        return None


def validation_run_url(repository, commit):
    """Address of a run that validated this commit, or None when none did."""
    if commit == os.environ["GITHUB_SHA"]:
        return f"https://github.com/{repository}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    runs = api(f"repos/{repository}/actions/workflows/marketplace-catalog.yml/runs"
               f"?head_sha={commit}&status=success&per_page=1")
    if runs["total_count"] == 0:
        return None
    return runs.get("workflow_runs", [{}])[0].get("html_url", "")


def pull_request_body(release_url, run_url):
    """The upstream pull request template, filled in. The HACS bot closes anything else."""
    return (
        "## Checklist\n\n"
        "- [x] I've read the [publishing documentation](https://hacs.xyz/docs/publish/start).\n"
        "- [x] I've added the [HACS action](https://hacs.xyz/docs/publish/action) to my repository.\n"
        "- [x] (For integrations only) I've added the [hassfest action]"
        "(https://developers.home-assistant.io/blog/2020/04/16/hassfest/) to my repository.\n"
        "- [x] The actions are passing without any disabled checks in my repository.\n"
        "- [x] I've added a link to the action run on my repository below in the links section.\n"
        "- [x] I've created a new release of the repository after the validation actions were run "
        "successfully.\n\n"
        "## Links\n\n"
        f"Link to current release: <{release_url}>\n"
        f"Link to successful HACS action (without the `ignore` key): <{run_url}>\n"
        f"Link to successful hassfest action (if integration): <{run_url}>\n\n"
        f"<!-- tid:{TEMPLATE_ID} -->"
    )


def proposed_catalog(content, repository):
    entries = json.loads(base64.b64decode(content))
    if repository in entries:
        return None
    return json.dumps(sorted([*entries, repository], key=str.lower), indent=2) + "\n"


def main():
    repository = os.environ["GITHUB_REPOSITORY"]
    submit = "--submit" in sys.argv
    if submit and not os.environ.get("GH_TOKEN"):
        raise ValueError("Submitting needs the repository secret CATALOG_SUBMISSION_TOKEN: a classic "
                         "token of the repository owner with the public_repo scope")
    upstream = api(f"repos/{UPSTREAM}")
    branch = upstream["default_branch"]
    sha = api(f"repos/{UPSTREAM}/git/ref/heads/{branch}")["object"]["sha"]
    listing = api(f"repos/{UPSTREAM}/contents/integration?ref={sha}")
    proposed = proposed_catalog(listing["content"], repository)
    output = Path(".marketplace-submission")
    output.mkdir(exist_ok=True)
    if proposed is None:
        (output / "status.md").write_text(f"{repository} is already listed in {UPSTREAM}.\n")
        print("Repository already listed.")
        return
    release = latest_release(repository)
    (output / "integration").write_text(proposed, encoding="utf-8")
    (output / "instructions.md").write_text(
        f"Repository {repository}\n\nLatest stable release: "
        f"{release['html_url'] if release else 'none yet, publish one first'}\n\n"
        "To submit, publish a stable release, make sure this workflow succeeded for the commit "
        "of that release (the commit it ran on counts), then run it again on the default branch "
        "with submit and publishing_docs_read enabled. Configure CATALOG_SUBMISSION_TOKEN with a "
        "user token that can create a public fork and pull request.\n", encoding="utf-8")
    if not submit:
        return
    owner = repository.split("/")[0]
    if api("user")["login"].lower() != owner.lower():
        raise ValueError("Submit with the repository owner's user token")
    if release is None:
        raise ValueError("Publish a stable release before submitting")
    commit = api(f"repos/{repository}/commits/{quote(release['tag_name'], safe='')}")["sha"]
    run_url = validation_run_url(repository, commit)
    if run_url is None:
        raise ValueError("Run the Marketplace catalog workflow on the commit of the latest release first")
    body = pull_request_body(release["html_url"], run_url)
    head = f"add-{repository.replace('/', '-')}"
    existing = api(f"repos/{UPSTREAM}/pulls?state=open&head={owner}:{head}")
    if existing:
        print(existing[0]["html_url"])
        return
    fork = api(f"repos/{UPSTREAM}/forks", {})
    fork_repo = fork["full_name"]
    for attempt in range(12):
        try:
            api(f"repos/{fork_repo}/git/ref/heads/{branch}")
            break
        except subprocess.CalledProcessError:
            if attempt == 11:
                raise
            time.sleep(5)
    try:
        api(f"repos/{fork_repo}/git/refs", {"ref": f"refs/heads/{head}", "sha": sha})
    except subprocess.CalledProcessError:
        current = api(f"repos/{fork_repo}/contents/integration?ref={head}")
        if base64.b64decode(current["content"]).decode() != proposed:
            raise ValueError("Existing submission branch differs. Review it before retrying.")
        result = api(f"repos/{UPSTREAM}/pulls", {
            "title": f"Add {repository}", "head": f"{owner}:{head}", "base": branch, "body": body,
        })
        print(result["html_url"])
        return
    blob = api(f"repos/{fork_repo}/git/blobs", {"content": proposed, "encoding": "utf-8"})
    base_tree = api(f"repos/{UPSTREAM}/git/commits/{sha}")["tree"]["sha"]
    tree = api(f"repos/{fork_repo}/git/trees", {"base_tree": base_tree, "tree": [
        {"path": "integration", "mode": "100644", "type": "blob", "sha": blob["sha"]},
    ]})
    commit = api(f"repos/{fork_repo}/git/commits", {
        "message": f"Add {repository}", "tree": tree["sha"], "parents": [sha],
    })
    api(f"repos/{fork_repo}/git/refs/heads/{head}", {"sha": commit["sha"]}, method="PATCH")
    result = api(f"repos/{UPSTREAM}/pulls", {
        "title": f"Add {repository}", "head": f"{owner}:{head}", "base": branch, "body": body,
    })
    print(result["html_url"])


if __name__ == "__main__":
    main()
