# Renovate

The Renovate GitHub app is installed for the repositories and reads `.github/renovate.json` of
each one. A self-hosted server is prepared as an alternative; it is not running.

| File | Purpose |
| --- | --- |
| [`default.json`](../default.json) | The shared rules: the one place to change them |
| `.github/renovate.json` | Generated from `default.json` by [`managed.py`](../.scripts/managed.py), in full, and kept in step by CI |
| [`.templates/renovate/self-hosted.js`](../.templates/renovate/self-hosted.js) | Server configuration with the repository list, for a self-hosted run |

## Why every repository carries the whole preset

A repository can extend a preset (`"extends": ["github>seb5594/hass-workflows"]`), but Renovate does not
load a preset from a private repository for a public one. The result is an issue titled "Action
Required: Fix Renovate Configuration" with *Cannot find preset's package*, and no pull requests.
This engine is private, so the preset is copied into each repository instead. To change a rule,
edit `default.json` and run `managed.py sync` in each repository.

## Branches

Renovate names its branches `feat/<topic>`, for example `feat/github-actions` or
`feat/alpine-base-and-packages`, one stable name per group of updates.

Only the default branch is a base branch (`baseBranchPatterns: ["$default"]`). The GitHub app can carry
base branches of its own from its portal settings; a branch a repository does not have shows up as
"Base branch does not exist" in the dashboard and puts `main` into every branch name.

## What the preset updates

- GitHub Actions in workflows, grouped into one pull request.
- The pinned `ghcr.io/home-assistant/base` tag in app Dockerfiles, grouped with the Alpine packages.
- Alpine packages pinned as `name=version`, via the Repology data source. Mark each one with
  `# renovate: datasource=repology depName=alpine_3_24/<package>` on the line above it.
- Other pinned tools marked the same way, such as `git-secrets` (`datasource=github-tags`).
- The engine's own Python (`python-version` of the setup action) and the `runs-on` Ubuntu version are not updated: both are raised on purpose.
- `requirements` in a `manifest.json` are not updated: changing what users install is a release decision.
- The base image tag `3.24-2026.08.0` moves within its Alpine release only (`3.24-2026.10.0`); the floating tag `3.24` is never proposed.

Renovate never changes `version` in `config.yaml`, the changelog, or `manifest.json`. Raise the
app version yourself when you merge a dependency update that should reach users.

The `alpine_3_24` part of the marker names the Alpine release. Change it together with the base
image when moving to a newer Alpine.

## Self-hosted server

Only needed instead of the app.

1. Create a fine-grained token for the Renovate account with **Contents**, **Pull requests**,
   **Issues** and **Workflows** (all read and write) on the repositories listed in
   `self-hosted.js`, and a second classic token without scopes for `GITHUB_COM_TOKEN`
   (release notes, avoids rate limits).
2. Run the official image on a schedule, for example every four hours:

   ```bash
   docker run --rm \
     -e RENOVATE_TOKEN -e GITHUB_COM_TOKEN \
     -e RENOVATE_CONFIG_FILE=/config.js \
     -v "$PWD/self-hosted.js:/config.js:ro" \
     renovate/renovate:latest
   ```

   Pin the image to a version tag once the setup works. Home Assistant OS users can run it as a
   cron-triggered container on any always-on machine; it needs no inbound connection.
3. Dependabot and Renovate both open pull requests for the same updates, and Dependabot names its branches `dependabot/…` with a hash. Remove `.github/dependabot.yml` from each project when Renovate is the only tool. The
   engine still keeps that file in step, so drop it from `shared_files()` in [`managed.py`](../.scripts/managed.py)
   at the same time.
