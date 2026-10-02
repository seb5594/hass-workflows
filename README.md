# Central Workflows & Infrastructure Engine

This repository hosts private reusable workflows, deployment helpers, and automation engines for the Home Assistant ecosystem maintained by [@seb5594](https://github.com/seb5594).

## Included Reusable Workflows
- `engine-app-ci.yml`: Code quality checks (Yamllint, ShellCheck, Hadolint) and container build tests.
- `engine-app-release.yml`: Multi-architecture container build & push to GitHub Container Registry (GHCR) and dispatch update.
- `engine-integration-ci.yml`: HACS validation and code quality checks for Custom Components.
- `engine-dashboard-generator.yml`: Automated multi-repository README telemetry and dashboard engine.
