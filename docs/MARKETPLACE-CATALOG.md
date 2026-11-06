# Marketplace catalog submissions

The generated integration workflow **Marketplace catalog** checks a public project
with the HACS action without ignored checks and with hassfest. Run it manually
from Actions. Private repositories and template repositories are excluded.
The workflow creates a submission artifact containing the proposed upstream
integration list and instructions.

For submission, publish a stable release, make sure the workflow succeeded for the
commit of that release (a run on that commit counts, whether before or after the release;
the default branch may already be further ahead), then rerun on the default branch with
**submit** and **publishing_docs_read** enabled. The submission step requires
**CATALOG_SUBMISSION_TOKEN** (a repository secret): a classic personal access token of
the repository owner with the `public_repo` scope, which allows creating a public fork,
updating its branch and opening the upstream pull request. Without the secret the
submission stops immediately with a message saying so. The regular validation uses the repository token.

The script checks that the release commit was validated, preserves the existing upstream list and reuses an open submission. An existing
branch with different contents requires review before retrying. Upstream review
and acceptance are handled by the HACS maintainers.

The workflow is only generated for integrations that qualify. Templates, forks and
integrations that replace a Core integration are listed with their reason in
`DEFAULT_CATALOG_EXCLUDED` (`.scripts/config.py`); catalogs and the hub never get it.
Excluded projects keep their custom-repository link. Projects need their own license, topics and
brand assets before the complete validation can pass.

[Publishing requirements](https://contributors.home-assistant.io/marketplace/guides/catalog/)
