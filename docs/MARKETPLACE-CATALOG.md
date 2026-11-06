# Marketplace catalog submissions

The generated integration workflow **Marketplace catalog** checks a public project
with the HACS action without ignored checks and with hassfest. Run it manually
from Actions. Private repositories and template repositories are excluded.
The workflow creates a submission artifact containing the proposed upstream
integration list and instructions.

For submission, run validation successfully, publish a release from that same
commit, then rerun on the default branch with **submit** and
**publishing_docs_read** enabled. The submission step requires
**CATALOG_SUBMISSION_TOKEN**, a GitHub user token owned by the repository owner
with permission to create a public fork, update its branch and open an upstream
pull request. The regular validation uses the repository token.

The script checks the release commit and the earlier successful validation run,
preserves the existing upstream list and reuses an open submission. An existing
branch with different contents requires review before retrying. Upstream review
and acceptance are handled by the HACS maintainers.

The official catalog excludes integrations that replace a Core integration.
PulseAudio Loopback Extended currently uses a Core domain and should continue
using its custom-repository link. Projects need their own license, topics and
brand assets before the complete validation can pass.

[Publishing requirements](https://contributors.home-assistant.io/marketplace/guides/catalog/)
