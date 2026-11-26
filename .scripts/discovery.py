"""Find the owner's public repositories whose names fit a catalog kind."""
import config
import github_api


def public_repositories(pattern, excluded=()):
    """Public, active repositories of the owner matching `pattern`, sorted by name.

    Walks every API page instead of relying on search indexing. Private, archived and disabled
    repositories are never returned, so a public listing cannot reveal that they exist.
    """
    owner = config.OWNER
    repositories, page = [], 1
    while True:
        batch = github_api.fetch_json(f"https://api.github.com/users/{owner}/repos"
                                      f"?type=owner&sort=full_name&per_page=100&page={page}")
        if not isinstance(batch, list):
            raise ValueError("Expected a repository list from GitHub.")
        repositories.extend(
            repo for repo in batch
            if repo["owner"]["login"].casefold() == owner.casefold()
            and pattern.fullmatch(repo["name"])
            and not (repo.get("private") or repo.get("archived") or repo.get("disabled"))
            and repo["name"] not in excluded)
        if len(batch) < 100:
            break
        page += 1
    return sorted(repositories, key=lambda repo: repo["name"].casefold())
