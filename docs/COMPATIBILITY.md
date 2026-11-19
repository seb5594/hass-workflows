# Home Assistant compatibility

The managed `compat.yml` runs daily at 05:41 UTC, on relevant code/test/workflow
changes, and manually. GitHub schedules may be delayed; discovery happens each run,
not through a release webhook in the upstream repository.

A project's explicit `homeassistant` minimum in `hacs.json` sets the lower bound.
This includes newer declarations such as 2023.6.0: targets below that supported
boundary are not selected. An older declaration also remains authoritative.
Without a declaration, the matrix uses a rolling five-year window
(`SUPPORT_YEARS` in `ha_matrix.py`). The curated release at or below that window's
oldest series is the first target, so the fallback moves with the calendar.
The CLI `--minimum` option remains an explicit override.

`ha_matrix.py list --live --matrix` retains the historical Python/API boundaries
in `ha_releases.json` and adds the newest non-yanked stable Home Assistant package
on PyPI. It also adds the newest published alpha/dev, beta and release candidate
newer than stable, when available. Unpublished channels are not invented. Discovery
or metadata errors fail the workflow instead of silently falling back to stale targets.

The discovery job freezes the exact Core, test plugin and Python minor in the matrix
and records them in its job summary. Workers use those objects without rediscovery.
PyPI `requires_python` metadata selects Python; uv installs that minor's current patch.
Historical targets retain their tested plugin and dependency pins.

When PyPI has a matching `pytest-homeassistant` release, the runner uses Core's
official fixtures at that exact version, including previews and Bluetooth extras.
From Core 2026.11.0 onward, if the matching fixture wheel is missing, discovery resolves
the official Core release tag to a commit. The worker fetches only the package files,
runs Core's own version-stamping script, and checks the fixture version and exact Core
dependency before installing it alongside the published Core wheel. The matrix records
the source commit. Once the matching wheel is published it takes precedence.
It exposes the legacy helper import path for existing project tests. On older
Core releases the runner uses `pytest-homeassistant-custom-component`.
If that plugin already tracks a preview, stable Core instead uses a matching plugin
from the latest 30 published plugin versions, when available.
When Core is ahead of its exact dependency pin, uv explicitly overrides only the Core
requirement. All other dependencies are resolved normally, and the installed Core
version is checked before testing. A failure can therefore mean the test harness
needs an update as well as an integration incompatibility. The logs say when this
forward-testing override is necessary.

Every target runs the regular and real Home Assistant suites. Preview failures are
visible failures, not ignored successes. Jobs use `fail-fast: false` so one broken
target does not hide the rest. This workflow does not publish integration releases.

## Minimum version in hacs.json

The whole window is tested, but `hacs.json` should only promise what passed. Each matrix target
leaves a small result artifact. On the default branch the `minimum` job reads them all with
[`ha_minimum.py`](../.scripts/ha_minimum.py) and writes the oldest release from which every
stable target up to the newest one passed (as `Y.M.0`) into `homeassistant`, then commits it as
`github-actions[bot]`. The value moves in both directions, so a fixed incompatibility lowers it
again on the next run. Nothing changes when the newest stable release fails (that is a
regression, not a boundary), when a result is missing, or for previews. Between two curated
release table entries the boundary is rounded up to the passing one. A target below the minimum that `hacs.json` already declares may fail without turning the
workflow red (it is shown as a notice); only releases the project claims to support do.
HACS reads the minimum from
`hacs.json`; a custom integration's `manifest.json` has no such key.

Integration callers follow the engine branch `main`, so a new engine state needs no commit
in the integration; `managed.py sync integration PATH` refreshes the callers after template
changes. Core versions are discovered live in any case: the package metadata is fetched live on every daily run.
