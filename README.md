# Central Workflows & Infrastructure Engine

This repository hosts private reusable workflows, deployment helpers, and automation engines for the Home Assistant ecosystem maintained by [@seb5594](https://github.com/seb5594).

## Included Reusable Workflows
- `engine-app-ci.yml`: Code quality checks (Yamllint, ShellCheck, Hadolint) and container build tests.
- `engine-app-release.yml`: Multi-architecture container build & push to GitHub Container Registry (GHCR) and dispatch update.
- `engine-integration-ci.yml`: HACS validation and code quality checks for Custom Components.
- `engine-dashboard-generator.yml`: Automated multi-repository README telemetry and dashboard engine.

## Public repositories and the private engine

GitHub does not allow a public repository to call a private reusable workflow
directly. Public entry workflows therefore check out this repository with
`ORCHESTRATION_PAT`, then run its local composite actions in `.actions/`.
Reusable workflow wrappers remain available for private callers.

Set `ORCHESTRATION_PAT` as an Actions secret in each app or integration repository.
The token needs read access to this private repository. App releases also use it
to send `update-addons` to `seb5594/Home-Assistant-Apps`, requiring write access to
that repository. Package publication and release creation use each source
repository's own `GITHUB_TOKEN` with job-scoped write permissions.

Fork pull requests do not receive this token and skip the private engine jobs.
Review the changes before running them on a trusted branch. Never combine
`pull_request_target` with a checkout of untrusted pull request code.

Public callers pin the engine checkout to a reviewed commit. After changing the
engine, update those pins. The app's `entrypoint.sh` is an exact vendored copy of
`.templates/entrypoint.sh`, so local Supervisor builds also work without access
to this private repository. CI checks that the copy is current.

## Release contract

- CI validates YAML, shell scripts and Dockerfiles, then builds amd64, aarch64,
  armv7, armhf and i386 images. Runtime regression tests run on amd64.
- App releases publish `ghcr.io/seb5594/{arch}-{slug}:{version}` after the whole
  build matrix passes. Local app builds remain supported without an image field.
- A new stable version on `main` creates its GitHub release automatically.
  Version tags and manual workflow dispatches are also supported; tag versions
  must match `config.yaml` or the integration manifest.
- Integration releases produce a HACS ZIP with the domain contents at its root,
  a manual ZIP containing `custom_components/{domain}`, and `SHA256SUMS.txt`.
  Existing ZIP releases are immutable; change the manifest version to publish
  an update.
- An already released app version on `main` is skipped. An explicit version tag
  can rebuild its container images, for example after a packaging correction.
- `engine-integration-release.yml` supplies the same ZIP publication for private
  reusable-workflow callers.
