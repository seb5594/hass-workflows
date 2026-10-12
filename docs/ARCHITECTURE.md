# Architecture

Everything with logic lives in [`.scripts`](../.scripts); the actions and caller workflows only
call it. Each module has one job.

| Module | Job |
| --- | --- |
| `config.py` | Owner, repository names, events, platforms, donation links, engine root: the only place for constants |
| `templating.py` | Fills `{{PLACEHOLDER}}` / `__PLACEHOLDER__` templates and fails on missing, unused or repeated names |
| `callers.py` | Renders, pins, syncs and checks the one workflow each repository keeps |
| `badgekit.py` | Badge builders and the layout lists that decide what appears where |
| `live.py` | Current counts (stars, issues, releases, downloads, runs) so empty badges are omitted |
| `excerpt.py` | First README paragraph as a short description |
| `remote.py` | Reads project metadata from GitHub at an exact commit, without cloning |
| `github_api.py` | The single HTTP client: retries, tokens, JSON and text |
| `gitops.py` | Commit, push and repository_dispatch used by catalog, hub and the README refresh |
| `readme.py` | Badge block below the title; thanks and license as the last two sections |
| `licenses.py` | Finds and names the license file; the license section of projects and the note of catalogs and hub |
| `project.py` | Entry point of the project action: inspect, validate, build, package, release, refresh |
| `legacy.py` | Architectures only the previous base images cover (armv7, armhf, i386): their base and package pins |
| `build_app.py`, `release_app.py`, `package_integration.py`, `validate_app.py` | App and integration specifics |
| `ha_matrix.py`, `hass_real_tests.py`, `ha_releases.json` | Test an integration against genuine Home Assistant releases: environments, the shared pytest plugin and the release table |
| `metrics.py` | Measurements of a run (tests, sizes, pulls) kept in the project's `.github/metrics.json` |
| `catalog.py`, `hub.py` | Catalog and hub generation |

## Flow

```
project push ──► project action ──► validate · build/package · release · README refresh
                                          │ release
                                          ▼
                           catalog (apps | integrations) ──► hub
```

Shared rules are written once: a new badge is one entry in `APP_LAYOUT` or `INTEGRATION_LAYOUT`, a
new repository name one line in `config.py`, a new caller family one template plus one entry in
`CALLERS`. Tests for each module sit in [`.github/tests`](../.github/tests).
