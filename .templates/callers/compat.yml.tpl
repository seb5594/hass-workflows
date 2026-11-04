name: Compatibility

on:
  push:
    branches: [main, dev]
    paths: ['custom_components/**', '.github/ha_tests/**', 'tests_ha/**', '.github/tests/**', '.github/workflows/compat.yml', 'hacs.json']
  pull_request:
    paths: ['custom_components/**', '.github/ha_tests/**', 'tests_ha/**', '.github/tests/**', '.github/workflows/compat.yml', 'hacs.json']
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
      - id: releases
        uses: ./.engine/.actions/ha-targets

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
      - uses: ./.engine/.actions/ha-test
        with:
          target: ${{ toJSON(matrix) }}
