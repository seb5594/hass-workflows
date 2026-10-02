"""Fill text templates and fail loudly when a placeholder is missing, unknown or repeated."""
import re

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
