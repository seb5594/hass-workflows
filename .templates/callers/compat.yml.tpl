name: Compatibility

on:
  push:
    branches: [main, dev]
    paths: ['custom_components/**', '.github/ha_tests/**', 'hacs.json']
  pull_request:
    paths: ['custom_components/**', '.github/ha_tests/**', 'hacs.json']
  schedule:
    - cron: '41 5 * * 1' # Weekly: a new Home Assistant release can break an integration.
  workflow_dispatch:

permissions:
  contents: read

jobs:
  releases:
    # include: fork-guard
    runs-on: ubuntu-latest
    outputs:
      releases: ${{ steps.releases.outputs.releases }}
    steps:
      # include: checkout-project
      # include: checkout-engine
      - id: releases
        run: echo "releases=$(python .engine/.scripts/ha_matrix.py list)" >> "$GITHUB_OUTPUT"

  test:
    needs: releases
    if: needs.releases.outputs.releases != '[]'
    name: Home Assistant ${{ matrix.release }}
    runs-on: ubuntu-latest
    timeout-minutes: 30
    strategy:
      fail-fast: false
      matrix:
        release: ${{ fromJSON(needs.releases.outputs.releases) }}
    steps:
      # include: checkout-project
      # include: checkout-engine
      - uses: ./.engine/.actions/setup-python
        with:
          packages: uv
      - run: python .engine/.scripts/ha_matrix.py run "${{ matrix.release }}"
