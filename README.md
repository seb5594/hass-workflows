# Central Workflows & Infrastructure Engine

This repository hosts private reusable workflows, deployment helpers, and automation engines for the Home Assistant ecosystem maintained by [@seb5594](https://github.com/seb5594).

## Architecture & Workflows
- `.github/workflows/engine-app-ci.yml`: Automated CI/CD build pipeline for Home Assistant Apps/Add-ons.
- `.github/workflows/engine-integration-ci.yml`: HACS validation and code quality checks for Custom Components.
- `.github/workflows/engine-dispatch-update.yml`: Cross-repository event trigger via GitHub Repository Dispatch.
- `.github/workflows/engine-dashboard-generator.yml`: Automated multi-repository README telemetry and dashboard engine.
- `.templates/entrypoint.sh`: Standardized container entrypoint script for Home Assistant Add-ons.
- `scripts/generate_readme.py`: Python generator for generating modular ecosystem READMEs.
