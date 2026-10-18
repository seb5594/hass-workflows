"""The picture below a README's title: the project's logo, or its icon when there is no logo.

Apps keep `logo.png` / `icon.png` in their folder, integrations in `brand/` of the component
(or, as a fallback, directly in its folder). Home Assistant's `@2x` and `dark_` variants are
used when present: the sharp file is shown at half its pixel size, the dark one on dark themes.
"""
import html
import struct
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import config
from projectmeta import APP

NAMES = ("logo", "icon")  # in order of preference
MAX_WIDTH, MAX_HEIGHT = 360, 160
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class Image:
    light: str
    dark: str | None
    width: int
    height: int


def png_size(path):
    """(width, height) from the PNG header."""
    header = path.read_bytes()[:24]
    if header[:8] != PNG_SIGNATURE:
        raise ValueError(f"{path} is not a PNG file")
    return struct.unpack(">II", header[16:24])


def directories(project):
    return [project.folder] if project.kind == APP else [project.folder / "brand", project.folder]


def fit(width, height):
    """Scale down into the box every logo shares; never scale up."""
    factor = min(1, MAX_WIDTH / width, MAX_HEIGHT / height)
    return round(width * factor), round(height * factor)


def find(project):
    """The preferred picture of the project, or None when it ships neither logo nor icon."""
    for name in NAMES:
        for directory in directories(project):
            if not (directory / f"{name}.png").is_file():
                continue
            sharp = directory / f"{name}@2x.png"
            scale, file = (2, sharp) if sharp.is_file() else (1, directory / f"{name}.png")
            width, height = png_size(file)
            dark = directory / f"dark_{file.name}"
            return Image(file.relative_to(project.root).as_posix(),
                         dark.relative_to(project.root).as_posix() if dark.is_file() else None,
                         *fit(width / scale, height / scale))
    return None


def raw_url(repository, relative):
    return f"https://raw.githubusercontent.com/{repository}/{config.DEFAULT_BRANCH}/{quote(relative, safe='/@')}"


def render(project):
    """HTML for the centered picture; empty when the project has none."""
    image = find(project)
    if image is None:
        return ""
    tag = (f'<img src="{raw_url(project.repository, image.light)}" alt="{html.escape(project.name)}" '
           f'width="{image.width}" height="{image.height}">')
    if image.dark:
        tag = (f'<picture>\n    <source media="(prefers-color-scheme: dark)" '
               f'srcset="{raw_url(project.repository, image.dark)}">\n    {tag}\n  </picture>')
    return f'<p align="center">\n  {tag}\n</p>'
