# Home Assistant compatibility

The managed `compat.yml` runs daily at 05:41 UTC, on relevant code/test/workflow
changes, and manually. GitHub schedules may be delayed; discovery happens each run,
not through a release webhook in the upstream repository.

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

After changing the engine, regenerate integration callers with `managed.py sync
integration ENGINE_COMMIT PATH`. A pinned engine does not need further commits to
discover new Core versions: the package metadata is fetched live on every daily run.
