# Home Assistant compatibility

The managed `compat.yml` runs daily at 05:41 UTC, on relevant code/test/workflow
changes, and manually. GitHub schedules may be delayed; discovery happens each run,
not through a release webhook in the upstream repository.

Live discovery uses today's UTC date to find the newest testable stable patch already public
five calendar years ago. It retains the curated Python and API checkpoints in that window and
resolves an older declared minimum when matching fixtures exist. For each half-year without a
stable checkpoint, it looks for the newest published stable patch with matching fixtures.

Each run also selects the latest stable Core and the newest available alpha/dev, beta and RC
for each upcoming monthly series. The daily job summary shows the next calendar month's beta
and RC separately, including across December and January. An unpublished preview is reported
as pending. Once PyPI publishes it, the next discovery can test it.

Discovery resolves the engine's `main` branch once. All workers in the run use that commit
and the selected Core, fixture and Python minor from the matrix. The compatibility actions
pin the uv version. Python patch releases and transitive wheels are still resolved at installation.

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

Each target records a result artifact. On the default branch a complete, successful matrix can
update the minimum in `hacs.json`. A clean test failure below the existing minimum provides a
lower boundary. A supported-target failure, missing artifact or inconclusive environment prevents
the managed workflow from changing the minimum. Preview results never determine the stable floor.
A newer project commit supersedes results for the older checkout.

### Exact patch boundary

Starting from the highest failing stable checkpoint and the next passing one, the minimum job
bisects the published, non-yanked stable patches strictly between them. It resolves fixtures and
builds an environment only when probing a candidate. PyPI metadata is reused within the process.
A probe without an installable matching environment is skipped. When every checkpoint passes,
the earliest observed passing patch supplies the minimum directly.

For example, a pass on `2022.8.7` can establish `2022.8.7`. Establishing `2022.8.0` requires
a pass on that version. With 31 testable candidates, bisection needs at most five additional
test runs. This search assumes a single failing-to-passing transition inside the gap. Isolated
regressions in untested patches can escape sampling.

The daily schedule, pushes and manual runs all use patch refinement. To inspect a plan locally,
run `python .engine/.scripts/ha_matrix.py list --live --matrix` from the integration checkout.
