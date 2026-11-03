name: Compatibility

on:
  push:
    branches: [main, dev]
    paths: ['custom_components/**', '.github/ha_tests/**', '.github/tests/**', '.github/workflows/compat.yml', 'hacs.json']
  pull_request:
    paths: ['custom_components/**', '.github/ha_tests/**', '.github/tests/**', '.github/workflows/compat.yml', 'hacs.json']
  schedule:
    - cron: '41 5 * * *' # Daily: discover new stable and alpha/beta/RC packages from PyPI.
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: compatibility-${{ github.ref }}
  cancel-in-progress: false

jobs:
  releases:
    # include: fork-guard
    runs-on: ubuntu-latest
    timeout-minutes: 10
    outputs:
      releases: ${{ steps.releases.outputs.releases }}
    steps:
      # include: checkout-project
      # include: checkout-engine
      - uses: ./.engine/.actions/setup-python
        with:
          packages: packaging==26.0
      - id: releases
        run: |
          targets=$(python .engine/.scripts/ha_matrix.py list --live --matrix)
          echo "releases=$targets" >> "$GITHUB_OUTPUT"
          printf '### Home Assistant targets\n\n```json\n%s\n```\n' "$targets" >> "$GITHUB_STEP_SUMMARY"

  test:
    needs: releases
    if: needs.releases.outputs.releases != '[]'
    name: Home Assistant ${{ matrix.homeassistant }}${{ matrix.preview && ' (preview)' || '' }}
    runs-on: ubuntu-latest
    timeout-minutes: 30
    strategy:
      fail-fast: false
      matrix:
        include: ${{ fromJSON(needs.releases.outputs.releases) }}
    steps:
      # include: checkout-project
      # include: checkout-engine
      - uses: ./.engine/.actions/setup-python
        with:
          packages: uv
      - name: Test selected Home Assistant release
        env:
          HA_TARGET: ${{ toJSON(matrix) }}
        run: python .engine/.scripts/ha_matrix.py run --target-json "$HA_TARGET"
