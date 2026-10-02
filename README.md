# Home Assistant Workflow Engine

[![Engine checks](https://img.shields.io/github/actions/workflow/status/seb5594/hass-workflows/engine-validation.yml?branch=main&label=engine%20checks)](https://github.com/seb5594/hass-workflows/actions/workflows/engine-validation.yml)
![Projects](https://img.shields.io/badge/projects-apps%20%2B%20integrations-1877A5)
![Architectures](https://img.shields.io/badge/builds-5%20architectures-157F71)
[![Buy Me a Coffee](https://img.shields.io/badge/Support-Buy%20Me%20a%20Coffee-FFDD00?logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/seb5594)
[![PayPal](https://img.shields.io/badge/Support-PayPal-0070BA?logo=paypal&logoColor=white)](https://www.paypal.com/donate/?hosted_button_id=QMQPNRENXDN26)

**One private engine for every Home Assistant project.** Public repositories keep a short workflow, their app/integration code, and the `.github/dependabot.yml` file GitHub requires locally. Metadata from `config.yaml` or `manifest.json` determines the validation, build, badges, and release behavior.

| Building block | Purpose |
| --- | --- |
| [Project action](.actions/project/action.yml) | Single CI and publishing entry point; detects the project type |
| [Project scripts](.scripts/project.py) | Metadata checks, five-architecture smoke tests, and release orchestration |
| [App templates](.templates/app/) / [integration templates](.templates/integration/) | Minimal public workflow and generated badge blocks |
| [Entrypoint](.templates/entrypoint.sh) | Shared startup code, copied into apps for standalone Supervisor builds |
| [Dependabot template](.templates/dependabot.yml) | Canonical copy for GitHub's mandatory per-repository configuration |

## Release flow

Apps build each declared platform, run shell/YAML/Docker lint and the available runtime tests, then publish architecture tags of the form `hass-APPNAMEVERSION-ARCH` in one stable GHCR package. For example, `ghcr.io/seb5594/hass-rsync-local:hass-rsync-local1.74.3-amd64`. A multi-platform `ghcr.io/seb5594/hass-rsync-local:1.74.3` tag resolves the correct architecture. Each version also gets a GitHub release with per-architecture image references; users can still build locally until prebuilt images are made public and selected in the app configuration.

Integrations run HACS checks, Python lint and tests. Every CI run produces verified HACS and manual-installation ZIP artifacts. A new manifest version publishes the two ZIPs and `SHA256SUMS.txt` as a GitHub release.

The build and smoke-test phase executes once per architecture. Publishing pushes the tested images instead of rebuilding them. A version already released on `main` remains unchanged; a matching `vVERSION` tag can republish app images deliberately.

## Public caller contract

The public workflow checks out this private repository at a reviewed commit through `ORCHESTRATION_PAT`. GitHub's Actions sharing switch does not grant `actions/checkout` access to a private secondary repository from a public caller. The token must select `hass-workflows` with **Contents: Read**. App catalog notifications also need **Contents: Read and write** for `Home-Assistant-Apps`. The source repository's `GITHUB_TOKEN` publishes its own release and images.

Fork pull requests cannot access the private engine and are skipped. The central [engine validation](.github/workflows/engine-validation.yml) checks both apps and the integration without publishing. Release ZIPs from these checks are available as workflow artifacts.

Each project's `.github/dependabot.yml` stays in that project: GitHub reads it there and cannot consume a template from another repository. Its contents are checked against [the shared template](.templates/dependabot.yml).

## Honest project metrics

Project READMEs show metadata-derived version, architecture, mounts, ingress when enabled, CI status, stars, and GitHub release-asset downloads. GHCR pulls, local Home Assistant builds, and installations are not counted by GitHub release badges. GitHub does not expose download country or continent data through its release API, so this engine does not invent geographic statistics.
