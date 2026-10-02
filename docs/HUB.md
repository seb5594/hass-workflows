# Hub

[`Home-Assistant-Hub`](https://github.com/seb5594/Home-Assistant-Hub) is the front page of everything published for Home Assistant. Like the catalogs it contains no logic: its workflow runs the [hub action](../.actions/hub/action.yml), which executes [`hub.py`](../.scripts/hub.py) and commits the generated `README.md`.

## Data flow

1. Read `.gitmodules` of the app and integration catalogs and the commit each submodule is pinned to.
2. Read the project's metadata at exactly that commit (`config.yaml`, or `manifest.json` and `hacs.json`) from `raw.githubusercontent.com`.
3. Render the overview tables into [`.templates/hub/README.md`](../.templates/hub/README.md).

Because the catalogs only pin public projects, private repositories never show up in the hub. The catalogs must be public themselves. A run that finds both catalogs empty fails instead of overwriting the README.

## Triggers

| Trigger | Behavior |
| --- | --- |
| Schedule | Every hour at minute 37, UTC |
| `update-hub` dispatch | Sent by a catalog after it committed a change, when `ORCHESTRATION_PAT` may write to the hub |
| Manual | **Actions → Update hub → Run workflow** |
| Edit of `update.yml` | For example a new engine pin |

The dispatch is best effort; without write access it only logs a warning and the hourly run catches up.
