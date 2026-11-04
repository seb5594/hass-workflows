name: Home Assistant CI

on:
  push:
    branches: [main, dev]
    tags: ['v*']
  pull_request:
  schedule:
    - cron: '23 4 * * 1' # Weekly: refreshes badge metrics and README values.
  workflow_dispatch:
    inputs:
      draft:
        description: Create the release as a draft for review
        type: boolean
        default: false

permissions:
  actions: read # Lets the README refresh see whether the workflow has run.
  contents: write
__PACKAGES__

jobs:
  pipeline:
    # include: fork-guard
    runs-on: ubuntu-latest
    timeout-minutes: __TIMEOUT__
    steps:
      # include: checkout-project
      # include: checkout-engine
      - uses: ./.engine/.actions/project
        with:
          token: ${{ github.token }}
          draft: ${{ inputs.draft }}
          catalog-token: ${{ secrets.ORCHESTRATION_PAT }}
