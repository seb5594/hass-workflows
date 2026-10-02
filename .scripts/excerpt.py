"""Short plain-text description taken from the first prose paragraph of a README."""
import html
import re

SKIPPED_STARTS = ("#", "[", "!", "<", "|", "---", "* ", "- ", ">")


def first_paragraph(markdown, limit=500, fallback=""):
    """First paragraph without headings, badges, comments or code, trimmed to `limit`."""
    paragraph, in_code, in_comment = [], False, False
    for line in markdown.splitlines():
        line = line.strip()
        in_comment = in_comment or "<!--" in line
        if in_comment:
            in_comment = "-->" not in line
            continue
        if line.startswith(("```", "~~~")):
            in_code = not in_code
            if paragraph:
                break
            continue
        if in_code:
            continue
        if not line or line.startswith(SKIPPED_STARTS):
            if paragraph:
                break
            continue
        paragraph.append(line)
    text = " ".join(paragraph) or fallback or "See the source repository for details."
    # Plain text keeps relative links and unresolved badge references out of catalogs.
    text = re.sub(r"!?\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]*>", "", text)
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    if len(text) > limit:
        text = text[:limit - 1].rsplit(" ", 1)[0] + "…"
    return html.escape(text, quote=False)
