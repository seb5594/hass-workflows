# Architecture

Everything with logic lives in [`.scripts`](../.scripts); the actions and caller workflows only
call it. Each module has one job.

| Module | Job |
| --- | --- |
| `config.py` | Owner, repository names, events, platforms, donation links, engine root: the only place for constants |
| `templating.py` | Fills `{{PLACEHOLDER}}` / `__PLACEHOLDER__` templates and fails on missing, unused or repeated names |
| `callers.py` | Renders, pins, syncs and checks the one workflow each repository keeps |
| `badgekit.py` | Badge builders and the layout lists that decide what appears where |
| `live.py` | Current counts (stars, releases, downloads, runs, published metrics) so empty badges are omitted |
| `excerpt.py` | First README paragraph as a short description |
| `remote.py` | Reads project metadata from GitHub at an exact commit, without cloning |
| `github_api.py` | The single HTTP client: retries, tokens, JSON and text |
| `gitops.py` | Commit, push and repository_dispatch used by catalog, hub and the README refresh |
| `readme.py` | Badge and thank-you blocks of a project README |
| `project.py` | Entry point of the project action: inspect, validate, build, package, release, refresh |
| `build_app.py`, `release_app.py`, `package_integration.py`, `validate_app.py` | App and integration specifics |
| `metrics.py` | Pipeline metrics as Shields endpoint files on the `badges` branch |
| `catalog.py`, `hub.py` | Catalog and hub generation |

## Flow

```
project push ──► project action ──► validate · build/package · release · metrics · README refresh
                                          │ release
                                          ▼
                           catalog (apps | integrations) ──► hub
```

Shared rules are written once: a new badge is one entry in `APP_LAYOUT` or `INTEGRATION_LAYOUT`, a
new repository name one line in `config.py`, a new caller family one template plus one entry in
`CALLERS`. Tests for each module sit in [`.github/tests`](../.github/tests).
