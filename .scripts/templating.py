"""Fill text templates and fail loudly when a placeholder is missing, unknown or repeated."""
import re
from pathlib import Path

BRACES = re.compile(r"\{\{([A-Z_]+)\}\}")
DUNDER = re.compile(r"__([A-Z]+(?:_[A-Z]+)*)__")


def fill(template, values, pattern=BRACES, once=True):
    """Replace every placeholder; with `once`, each may appear only a single time.

    A line that holds nothing but a placeholder disappears when its value is empty, so optional
    lines need no special handling in the template.
    """
    names = pattern.findall(template)
    unknown = sorted(set(names) - set(values))
    if unknown:
        raise ValueError(f"Template placeholders without a value: {', '.join(unknown)}")
    unused = sorted(set(values) - set(names))
    if unused:
        raise ValueError(f"Values the template does not use: {', '.join(unused)}")
    repeated = sorted({name for name in names if names.count(name) > 1}) if once else []
    if repeated:
        raise ValueError(f"Placeholders used more than once: {', '.join(repeated)}")
    lines = []
    for line in template.splitlines(keepends=True):
        match = pattern.fullmatch(line.strip()) if line.strip() else None
        if match and not values[match.group(1)]:
            continue
        lines.append(pattern.sub(lambda found: str(values[found.group(1)]), line))
    return "".join(lines)


INCLUDE = re.compile(r"^(?P<indent> *)# include: (?P<name>[a-z0-9-]+)[ \t]*$", re.M)


def expand_includes(template, snippets):
    """Replace every `# include: NAME` line by .templates/snippets/NAME.yml, indented like the line.

    A step that several workflows share is written once as a snippet. Includes are resolved
    before placeholders are filled, so a snippet may contain placeholders itself.
    """
    def snippet(match):
        path = Path(snippets) / f"{match['name']}.yml"
        if not path.is_file():
            raise ValueError(f"Template includes the unknown snippet {match['name']!r}")
        lines = path.read_text().rstrip("\n").splitlines()
        return "\n".join(match["indent"] + line if line else line for line in lines)

    return INCLUDE.sub(snippet, template)
