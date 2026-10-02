# Catalogs

Two catalog repositories share one script: [`Home-Assistant-Apps`](https://github.com/seb5594/Home-Assistant-Apps) (`kind: apps`) and [`Home-Assistant-Integrations`](https://github.com/seb5594/Home-Assistant-Integrations) (`kind: integrations`). Neither contains logic of its own. Its workflow checks out this engine and runs the [catalog action](../.actions/catalog/action.yml); everything below lives in [`catalog.py`](../.scripts/catalog.py) and [`.templates/catalog`](../.templates/catalog).

## Discovery rules

**Integrations** are repositories named `hass-<project>-integration` or `Home-Assistant-<project>-Integration` that contain `custom_components/*/manifest.json`. The rules below apply to both kinds; only the name pattern differs.

**Private repositories stay invisible.** Discovery drops private, archived and disabled repositories, so they appear neither in the README nor as submodules, and a repository that turns private disappears on the next run. GitHub renders a README identically for every viewer, so this is the only way to keep a public catalog from revealing them.

Only public, active repositories owned by `seb5594` are included. Names must match `Home-Assistant-<project>-App` or `Home-Assistant-<project>-Addon` with a nonempty project name. Matching is case-sensitive; forks owned by seb5594 are eligible.

| Repository name | Eligible? |
| --- | --- |
| `Home-Assistant-git-exporter-Addon` | Yes |
| `Home-Assistant-Example-App` | Yes |
| `Home-Assistant-App` / `Home-Assistant-Addon` | No: missing project name |
| `Home-Assistant-Apps` / `Home-Assistant-Addons` | No: plural suffix |
| A matching repository owned by another account | No |

Each project needs at least one app configuration, at its root or in a nested folder. Invalid metadata and duplicate slugs stop the run before anything is pushed.

## Triggers

| Trigger | Behavior |
| --- | --- |
| Schedule | Every hour at minute 17 (UTC) |
| Manual | **Actions → Synchronize app catalog → Run workflow** |
| `update-addons` / `update-integrations` dispatch | Sent after a release through `ORCHESTRATION_PAT` |
| Workflow change | A push that edits `update.yml` (for example a new engine pin) |

Unchanged results produce no commit. Apps created as submodules keep their pinned commit visible in the README.

## Changing the output

- Static text and the repository metadata: `.templates/catalog/apps` and `.templates/catalog/integrations`.
- Excluded repositories and excerpt length: constants at the top of `catalog.py`.
- Badge rows are shared with the project READMEs: [`badgekit.py`](../.scripts/badgekit.py).
- To use a new engine version, change `ref` in the catalog's `update.yml` to the commit.

Previously managed projects that are excluded, renamed, deleted, archived or made private are removed on the next successful run. An empty discovery result cannot erase an existing catalog.
