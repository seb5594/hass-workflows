# Dashboards

A *dashboard project* is everything visual that Home Assistant shows in Lovelace: a custom **card**
(HACS category *Dashboard*, which HACS still calls `plugin` internally) or a **theme**. Like apps and
integrations it needs no pipeline code of its own, the engine recognises it from its metadata.

## What a dashboard repository contains

| Path | Meaning |
| --- | --- |
| `hacs.json` | What HACS reads: `name`, `filename` (the one `.js` file of a card; a theme has none), `homeassistant` (minimum version), `render_readme` |
| `package.json` | The one place for `version` (calendar versions like `2026.11.26.1` work), `repository`, and the `build`, `lint` and `test` scripts |
| `package-lock.json` | Committed; CI installs with `npm ci` |
| `src/` | The card's source. `src/translations/en.json` is the key set every other `src/translations/*.json` must contain |
| `themes/*.yaml` | Themes only: one file per theme collection |
| `brand/` | `icon.svg` / `logo.svg` sources and the PNGs rendered from them with `node .engine/.scripts/render_brand.cjs brand brand`; the README header shows `logo`, else `icon` |
| `.github/workflows/ci.yml` | The caller, rendered by [`managed.py`](../.scripts/managed.py) like in every other repository |

A repository with `hacs.json` and `package.json` but neither an app nor a `custom_components` folder is a
dashboard project ([`projectmeta.py`](../.scripts/projectmeta.py)). With a `filename` it is a card, without one a theme.

## What the pipeline does

1. [`dashboard_checks.py`](../.scripts/dashboard_checks.py): `hacs.json` only has keys HACS accepts, the `filename` is one `.js` file, `package.json` has a valid version, a repository and (for cards) a `build` script, translations have the keys of English, brand images have sensible sizes, themes are mappings of theme names to variables.
2. `npm ci --ignore-scripts`, then the project's `lint` and `test` scripts when it has them. The number of passed tests becomes the *tests* badge.
3. `npm run build` must write `dist/<filename>`. Its size becomes the *bundle size* badge.
4. On the default branch a new version is released: the tag is the version (calendar versions without `v`), the card file is the only release asset, and the notes end with its SHA-256. An existing release is never touched.
5. After publishing, the HACS action checks the repository. It runs only then, because HACS installs a card from its release asset, so the check cannot pass before the first release exists.
6. The README header and the measurements are refreshed, and the hub is told to update.

Pull requests run steps 1 to 3 only. Releasing again after a failed run is safe, a version that exists is skipped.

## Versions

`YYYY.MM.DD` for the first build of a day, then `.1`, `.2`, and so on, exactly like integrations.
`python .engine/.scripts/calver.py bump` raises the version in `package.json`. npm accepts these versions in a private
package, but not on the registry: a card is released through HACS, so set `"private": true`.

## Catalog and hub

[`Home-Assistant-Dashboards`](https://github.com/seb5594/Home-Assistant-Dashboards) is the planned catalog; repositories named
`Home-Assistant-<project>-Card`, `-Lovelace-Card`, `-Dashboard` or `-Theme` (or `hass-…`) belong to it. Until it exists
(`config.UNCATALOGUED`), the [hub](HUB.md) finds them itself, so the first card shows up there immediately. When
the catalog repository is created, run `managed.py sync catalog-dashboards` in it. The hub switches over on its own as
soon as the catalog publishes `.github/catalog.json`, and releases notify the catalog instead of the hub
(`package_dashboard.notification_target`).

## Starting a new card

Copy an existing dashboard repository, change `name`, `repository` and the version in `package.json`, `hacs.json` and the
code, run `python .engine/.scripts/managed.py sync dashboard`, and register the repository in `PROJECTS["dashboards"]`
in [`config.py`](../.scripts/config.py).
