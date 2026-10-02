name: Validate and release __KIND__

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
    # Repository secrets are not passed to untrusted fork pull requests.
    if: github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository
    runs-on: ubuntu-latest
    timeout-minutes: __TIMEOUT__
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false
      - uses: actions/checkout@v7
        with:
          repository: __ENGINE_REPOSITORY__
          ref: __ENGINE_SHA__
          token: ${{ secrets.ORCHESTRATION_PAT }}
          path: .engine
          persist-credentials: false
      - uses: ./.engine/.actions/project
        with:
          token: ${{ github.token }}
          draft: ${{ inputs.draft }}
          catalog-token: ${{ secrets.ORCHESTRATION_PAT }}
