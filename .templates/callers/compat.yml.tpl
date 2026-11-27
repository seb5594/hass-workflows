name: Compatibility

on:
  push:
    branches: [main, dev]
    paths: ['custom_components/**', '.github/ha_tests/**', 'tests_ha/**', '.github/tests/**', 'tests/**', '.github/workflows/compat.yml', 'hacs.json']
  pull_request:
    paths: ['custom_components/**', '.github/ha_tests/**', 'tests_ha/**', '.github/tests/**', 'tests/**', '.github/workflows/compat.yml', 'hacs.json']
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
      engine: ${{ steps.releases.outputs.engine }}
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
    env:
      # This Core version pins lru-dict 1.1.7, which predates the stricter GCC default.
      CFLAGS: ${{ matrix.homeassistant == '2022.4.7' && '-Wno-error=incompatible-pointer-types' || '' }}
    strategy:
      fail-fast: false
      matrix:
        include: ${{ fromJSON(needs.releases.outputs.releases) }}
    steps:
      # include: checkout-project
      # include: checkout-frozen-engine
      - uses: ./.engine/.actions/ha-test
        with:
          target: ${{ toJSON(matrix) }}

  minimum:
    # Keep the verified floor when a supported target fails or the matrix is incomplete.
    needs: [releases, test]
    if: ${{ !cancelled() && needs.releases.result == 'success' && needs.test.result == 'success' && github.event_name != 'pull_request' && github.ref == format('refs/heads/{0}', github.event.repository.default_branch) }}
    runs-on: ubuntu-latest
    timeout-minutes: 60 # The boundary search builds a few extra environments.
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v7
      # include: checkout-frozen-engine
      - uses: actions/download-artifact@v8
        with:
          pattern: ha-result-*
          path: ${{ runner.temp }}/ha-results
          merge-multiple: true
      - uses: ./.engine/.actions/ha-minimum
        with:
          results: ${{ runner.temp }}/ha-results
          expected: ${{ needs.releases.outputs.releases }}
          refine: 'true'
