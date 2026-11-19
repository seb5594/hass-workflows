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

  minimum:
    # Not for pull requests, which cannot write, nor for forks.
    needs: [releases, test]
    if: ${{ !cancelled() && needs.releases.result == 'success' && github.event_name != 'pull_request' && github.ref == format('refs/heads/{0}', github.event.repository.default_branch) }}
    runs-on: ubuntu-latest
    timeout-minutes: 60 # The boundary search builds a few extra environments.
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v7
      # include: checkout-engine
      - uses: actions/download-artifact@v8
        with:
          pattern: ha-result-*
          path: ${{ runner.temp }}/ha-results
          merge-multiple: true
      - uses: ./.engine/.actions/ha-minimum
        with:
          results: ${{ runner.temp }}/ha-results
          expected: ${{ needs.releases.outputs.releases }}
          refine: ${{ github.event_name != 'schedule' }}
