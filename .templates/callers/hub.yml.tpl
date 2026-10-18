name: Update hub

on:
  schedule:
    - cron: '37 * * * *' # Every hour at minute 37 (UTC).
  workflow_dispatch:
  repository_dispatch:
    types: [__EVENT__] # Sent by the catalogs after they changed.
  push:
    branches: [main]
    paths: ['.github/workflows/update.yml']

permissions:
  actions: read
  contents: read

concurrency:
  group: update-hub
  cancel-in-progress: false

jobs:
  update:
    if: github.ref == format('refs/heads/{0}', github.event.repository.default_branch)
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      actions: read
      contents: write
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ github.event.repository.default_branch }}
          fetch-depth: 1
      # include: checkout-engine
      - uses: ./.engine/.actions/hub
        with:
          # Reads the catalogs even while they are private; only public projects end up listed.
          token: ${{ secrets.ORCHESTRATION_PAT }}
