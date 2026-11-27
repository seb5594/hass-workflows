"""Render GitHub release notes from the project's versioned changelog or first-parent history."""
import argparse
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote

# Order is also the reading order of a release.
SECTIONS = {
    "breaking": "💥 Breaking changes",
    "security": "🔒 Security",
    "feat": "✨ New features",
    "improve": "🎨 Improvements",
    "fix": "🐛 Bug fixes",
    "deps": "📦 Dependency updates",
    "docs": "📝 Documentation",
    "chore": "🔧 Maintenance",
    "other": "🔄 Other changes",
}
TYPES = {"perf": "improve", "refactor": "improve", "style": "improve", "ci": "chore",
         "test": "chore", "build": "chore", "enhancement": "improve"}
PREFIX = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?:\s+", re.I)
MERGE_PR = re.compile(r"^Merge pull request #(\d+) from (.+)$")
SQUASH_PR = re.compile(r" \(#(\d+)\)$")
BOT = re.compile(r"^(?:dependabot|renovate)(?:\[bot\]|-.+)?$", re.I)
WORDS = (
    ("breaking", r"breaking changes?\b"),
    ("security", r"security\b|patch CVE-"),
    ("deps", r"dependencies:|bump .+ from \S+ to \S+|bump the .+ group\b|"
             r"(?:update|upgrade|pin) .+ to v?\d|update upstream to release"),
    ("fix", r"fix(?:es|ed)?\b"),
    ("feat", r"add(?:s|ed)?\b|introduce(?:s|d)?\b"),
    ("improve", r"improve(?:s|d)?\b|optimi[sz]e(?:s|d)?\b|refactor\b"),
    ("docs", r"document(?:s|ed)?\b"),
)
HISTORY_LIMIT = 100
DEP_SCOPES = {"deps", "deps-dev"}
# Rewrite only the two unambiguous version-pair formats. Group updates keep their full titles.
PACKAGE = r"(?P<package>[@\w./-]+)"
VERSION = r"v?\d[\w.+-]*?"
DEPENDABOT_BUMP = re.compile(rf"Bump {PACKAGE} from (?P<old>{VERSION}) to (?P<new>{VERSION})(?P<path> in /\S*)?", re.I)
UPSTREAM_BUMP = re.compile(rf"Update {PACKAGE} to (?P<new>{VERSION}) \(was (?P<old>{VERSION})\)\.?", re.I)


def classify(title, *, dependency=False, body=""):
    """Return the section and readable title, retaining scopes and package version pairs."""
    kind = scope = None
    display_scope = None
    breaking = re.search(r"^BREAKING[ -]CHANGE:\s*\S", body, re.M)
    if prefix := PREFIX.match(title):
        kind, scope = prefix["type"].lower(), prefix["scope"]
        if kind in SECTIONS or kind in TYPES or scope in DEP_SCOPES:
            title = title[prefix.end():]
            display_scope = scope if scope not in DEP_SCOPES else None
        breaking = breaking or prefix["breaking"]
    for section, heading in SECTIONS.items():
        emoji = heading.split()[0]
        if title.startswith(emoji):
            title = title.removeprefix(emoji).lstrip()
            kind = section
            break
    if breaking or kind == "breaking":
        section = "breaking"
    elif kind == "security":
        section = "security"
    elif dependency or scope in DEP_SCOPES or kind == "deps":
        section = "deps"
    elif kind in SECTIONS or kind in TYPES:
        section = TYPES.get(kind, kind)
    else:
        section = next((key for key, pattern in WORDS if re.match(pattern, title, re.I)), "other")
    if section == "deps":
        title = re.sub(r"^Dependencies:\s*", "", title, flags=re.I)
        if bump := DEPENDABOT_BUMP.fullmatch(title) or UPSTREAM_BUMP.fullmatch(title):
            title = f"{bump['package']} · {bump['old']} → {bump['new']}" + (bump.groupdict().get("path") or "")
    if display_scope:
        title = f"{display_scope} · {title}"
    return section, title


def version_entry(markdown, version):
    """Extract an exact ATX version section, preserving nested Markdown and fenced examples."""
    heading = re.compile(rf"^\[?v?{re.escape(version)}\]?(?=$|\s|:)")
    lines = []
    depth = 0
    fence = ""
    for line in markdown.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence:
            if re.fullmatch(rf" {{0,3}}{fence[0]}{{{len(fence)},}}\s*", line):
                fence = ""
        elif marker:
            fence = marker[1]
        elif match := re.match(r"^(#{1,6})\s+(.+)", line):
            if depth and len(match[1]) <= depth:
                break
            if not depth and heading.match(match[2]):
                depth = len(match[1])
                continue
        if depth:
            lines.append(line)
    return "\n".join(lines).strip()


def sections(entries):
    groups = {key: [] for key in SECTIONS}
    for key, text in entries:
        groups[key].append(f"- {text}")
    return "\n\n".join(f"## {SECTIONS[key]}\n\n" + "\n".join(items)
                       for key, items in groups.items() if items)


def authored_notes(entry):
    # Keep each bullet with its continuation lines and sub-list. A mixed-format guide
    # (headings, prose or fenced examples) keeps the author's complete layout.
    items = []
    for line in entry.splitlines():
        if re.match(r"^[-*+]\s+", line):
            items.append([line[2:].lstrip()])
        elif items and (not line.strip() or line.startswith((" ", "\t"))):
            items[-1].append(line)
        else:
            return "## 📝 Release highlights\n\n" + entry
    entries = []
    for title, *continuation in items:
        kind, title = classify(title)
        entries.append((kind, "\n".join([title, *continuation]).rstrip()))
    return sections(entries)


def git(directory, *args):
    return subprocess.check_output(["git", "-C", directory, *args], text=True)


def history_notes(directory, revision, repo_url):
    log = git(directory, "log", "--first-parent", f"--max-count={HISTORY_LIMIT + 1}", "-z",
              "--format=%H%n%an%n%s%n%b", revision, "--")
    commits = log.removesuffix("\0").split("\0") if log else []
    entries = []
    for record in commits[:HISTORY_LIMIT]:
        sha, author, title, body = record.split("\n", 3)
        dependency = bool(BOT.fullmatch(author))
        if merge := MERGE_PR.match(title):
            pr = merge[1]
            dependency = dependency or bool(re.search(r"/(?:renovate|dependabot)/", merge[2]))
            title = next((line.strip() for line in body.splitlines() if line.strip()), title)
        elif squash := SQUASH_PR.search(title):
            pr = squash[1]
            title = title[:squash.start()]
        else:
            pr = None
        if title == "docs: refresh README badges":
            continue
        kind, text = classify(title, dependency=dependency, body=body)
        link = f"[#{pr}]({repo_url}/pull/{pr})" if pr else f"[`{sha[:7]}`]({repo_url}/commit/{sha})"
        # A commit subject is plain text; keep Markdown punctuation from changing the release layout.
        text = re.sub(r"([\\`*_\[\]<>|~])", r"\\\1", text[:400])
        entries.append((kind, f"{text} · {link}"))
    result = sections(entries)
    if len(commits) > HISTORY_LIMIT:
        result += f"\n\nShowing changes from the most recent {HISTORY_LIMIT} commits. See the full history below."
    elif not result and commits:
        result = "## 🔧 Maintenance\n\n- Refreshed the README badges."
    elif not commits:
        result = "This release points to the same commit as the previous version."
    return result.strip()


def render(directory, repo, tag, target, entry):
    # A version on a side branch or a tag at the release target must not hide the changes being shipped.
    previous = subprocess.run(["git", "-C", directory, "describe", "--tags", "--first-parent",
                               "--abbrev=0", "--match=[0-9]*", "--match=v[0-9]*", f"--exclude={tag}",
                               target], capture_output=True, text=True)
    base = previous.stdout.strip() if previous.returncode == 0 else ""
    revision = f"{base}..{target}" if base else target
    url = f"https://github.com/{repo}"
    notes = authored_notes(entry) if entry else history_notes(directory, revision, url)
    if base:
        footer = f"[Full changelog]({url}/compare/{quote(base, safe='')}...{quote(tag, safe='')})"
    else:
        footer = f"[Commit history]({url}/commits/{quote(target, safe='')})"
    return f"{notes}\n\n{footer}"


def generated_notes(repo, tag, target, changelog=None):
    entry = ""
    if changelog and changelog.is_file():
        entry = version_entry(changelog.read_text(encoding="utf-8"), tag.removeprefix("v"))
    if git(".", "rev-parse", "--is-shallow-repository").strip() == "false":
        return render(".", repo, tag, target, entry)
    # Existing callers check out one commit without credentials. Fetch only the commit graph
    # into a disposable bare repository so previewing or publishing never modifies their checkout.
    origin = git(".", "remote", "get-url", "origin").strip()
    with tempfile.TemporaryDirectory() as history:
        git(".", "init", "--quiet", "--bare", history)
        git(history, "-c", "credential.helper=", "-c", "credential.https://github.com.helper=!gh auth git-credential",
            "fetch", "--quiet", "--filter=tree:0", "--tags", origin, target)
        return render(history, repo, tag, target, entry)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", help="GitHub owner/repository of the current project checkout")
    parser.add_argument("tag")
    parser.add_argument("target", help="release commit SHA")
    parser.add_argument("--changelog", type=Path, help="app CHANGELOG.md")
    args = parser.parse_args()
    print(generated_notes(args.repo, args.tag, args.target, args.changelog))
