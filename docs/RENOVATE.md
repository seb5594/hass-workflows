# Renovate preparation

Everything needed for a self-hosted Renovate server is in place; nothing runs yet.

| File | Purpose |
| --- | --- |
| [`default.json`](../default.json) | Shared preset every project extends |
| `.github/renovate.json` ([template](../.templates/renovate/renovate.json)) | The only file a project needs; CI checks that it matches |
| [`.templates/renovate/self-hosted.js`](../.templates/renovate/self-hosted.js) | Server configuration with the repository list |

## What the preset updates

- GitHub Actions in workflows, grouped into one pull request.
- The pinned `ghcr.io/home-assistant/base` tag in app Dockerfiles, grouped with the Alpine packages.
- Alpine packages pinned as `name=version`, via the Repology data source. Mark each one with
  `# renovate: datasource=repology depName=alpine_3_24/<package>` on the line above it.
- Other pinned tools marked the same way, such as `git-secrets` (`datasource=github-tags`).

Renovate never changes `version` in `config.yaml`, the changelog, or `manifest.json`. Raise the
app version yourself when you merge a dependency update that should reach users.

The `alpine_3_24` part of the marker names the Alpine release. Change it together with the base
image when moving to a newer Alpine.

## Starting the server

1. Create a fine-grained token for the Renovate account with **Contents**, **Pull requests**,
   **Issues** and **Workflows** (all read and write) on the repositories listed in
   `self-hosted.js`, and a second classic token without scopes for `GITHUB_COM_TOKEN`
   (release notes, avoids rate limits). The preset lives in this private repository, so the
   first token must also be able to read `hass-workflows`.
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
3. Remove `.github/dependabot.yml` from each project in the same change that goes live. The
   engine currently requires that file, so drop the check in [`project.py`](../.scripts/project.py)
   at the same time. Running both tools produces duplicate pull requests.
