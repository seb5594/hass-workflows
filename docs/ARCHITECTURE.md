# Architecture

Everything with logic lives in [`.scripts`](../.scripts); the actions and caller workflows only
call it. Each module has one job.

| Module | Job |
| --- | --- |
| `config.py` | Owner, repository names, events, platforms, donation links, engine root: the only place for constants |
| `templating.py` | Expands `# include: NAME` snippets and fills `{{PLACEHOLDER}}` / `__PLACEHOLDER__` templates; fails on missing, unused or repeated names |
| `projectmeta.py` | The one model of a checkout: kind (app, integration or dashboard), folder, metadata, repository |
| `managed.py` | Renders, syncs and checks the files every repository keeps: workflows, Dependabot, Renovate, funding, entrypoint |
| `brand.py` | Picks the README picture: logo, else icon, with `@2x` and dark variants |
| `plan.py` | The job matrix of the engine's own validation, from `config.PROJECTS` |
| `badgekit.py` | Badge builders, the three row sizes and the layout lists that decide what appears where |
| `live.py` | Current counts (stars, issues, releases, downloads, runs) so empty badges are omitted |
| `excerpt.py` | First README paragraph as a short description |
| `remote.py` | Reads project metadata from GitHub at an exact commit, without cloning |
| `github_api.py` | The single HTTP client: retries, tokens, JSON and text |
| `gitops.py` | Commit, push and repository_dispatch used by catalog, hub and the README refresh |
| `readme.py` | Header (name, logo, separator, badges) at the top; thanks and license as the last two sections |
| `licenses.py` | Finds and names the license file; the license section of projects and the note of catalogs and hub |
| `project.py` | Entry point of the project action: inspect, validate, build, package, release, refresh |
| `legacy.py` | Architectures only the previous base images cover (armv7, armhf, i386): their base and package pins |
| `build_app.py`, `release_app.py`, `package_integration.py`, `validate_app.py` | App and integration specifics |
| `package_dashboard.py`, `dashboard_checks.py` | Dashboard specifics: build the card, publish its one release file, rules for `hacs.json`, `package.json`, themes and translations, see [Dashboards](DASHBOARDS.md) |
| `discovery.py` | The owner's public repositories whose names fit a catalog kind; shared by catalogs and the hub |
| `ha_matrix.py`, `hass_real_tests.py`, `ha_releases.json` | Test an integration against genuine Home Assistant releases: environments, the shared pytest plugin and the release table |
| `integration_checks.py` | Rules every integration shares: `strings.json` mirrors `translations/en.json`, other languages have the same keys, `services.yaml` matches the service texts, the ZIP is named after the domain, brand images have Home Assistant's sizes |
| `render_brand.cjs` | Renders `icon.svg` / `logo.svg` (and `dark_` variants) into `brand/*.png` and `@2x` files with Playwright |
| `metrics.py` | Measurements of a run (tests, sizes, pulls) kept in the project's `.github/metrics.json` |
| `catalog.py`, `hub.py` | Catalog and hub generation |

## Flow

```
project push ──► project action ──► validate · build/package · release · README refresh
                                          │ release
                                          ▼
                    catalog (apps | integrations | dashboards) ──► hub
```

Shared rules are written once: a new badge is one entry in `APP_LAYOUT` or `INTEGRATION_LAYOUT`, a
new repository name one line in `config.py`, a new caller family one template plus one entry in
`WORKFLOWS`, a step several workflows share one file in `.templates/snippets`. Tests for each module sit in [`.github/tests`](../.github/tests).
