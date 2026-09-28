"""`ostler doctor`'s check that a section type which lives on one page type only appears on no other page."""

from __future__ import annotations

from ostler import markdown, registry
from ostler.finding import Finding


def check_section_hosts(doc: markdown.MarkdownDoc, rel: str, page_type: str,
                        f: list[Finding]) -> None:
    """A section type that lives on one page type only (an endpoint on a server) appears on no other page."""
    for section in doc.walk_sections():
        title = section.title.strip()
        stype = registry.UI_TYPES_BY_NAME.get(registry.UI_HEADING_TO_TYPE.get(title, ""))
        if stype is None or not stype.host_page_types or page_type in stype.host_page_types or not section.children:
            continue
        host = " or ".join(stype.host_page_types)
        f.append(Finding(
            "error", "misplaced-section",
            f"{rel}: a {page_type} page holds `{'#' * section.level} {title}`, but a "
            f"{stype.name} lives only on a {host} page. A copy here drifts from the one the "
            f"{host} page describes, and a flow step that walks it drives the copy. Move each "
            f"one's claims onto the "
            f"matching {stype.name} of the {host} page, delete this section, and link that "
            f"{stype.name} from here instead",
            path=rel, line=doc.body_offset + section.line_start + 1, ref=title))
