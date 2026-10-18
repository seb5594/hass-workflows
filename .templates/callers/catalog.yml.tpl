name: Synchronize __TITLE__ catalog

on:
  schedule:
    - cron: '17 * * * *' # Every hour at minute 17 (UTC).
  workflow_dispatch:
  repository_dispatch:
    types: [__EVENT__] # Sent by the __TITLE__ repositories after a release.
  push:
    branches: [main]
    paths: ['.github/workflows/update.yml']

permissions:
  actions: read
  contents: read

concurrency:
  group: synchronize-__TITLE__-catalog
  cancel-in-progress: false # Serialize writes; never cancel a running synchronization.

jobs:
  synchronize:
    if: github.ref == format('refs/heads/{0}', github.event.repository.default_branch)
    runs-on: ubuntu-latest
    timeout-minutes: 20
    permissions:
      actions: read
      contents: write
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ github.event.repository.default_branch }}
          submodules: false # The catalog script initializes and verifies each source itself.
          fetch-depth: 1
      # include: checkout-engine
      - uses: ./.engine/.actions/catalog
        with:
          kind: __KIND__
          token: ${{ github.token }}
          hub-token: ${{ secrets.ORCHESTRATION_PAT }}
