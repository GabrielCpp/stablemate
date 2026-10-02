"""`ostler doctor`'s check that every endpoint page names one server page and that server lists it."""

from __future__ import annotations

from pathlib import Path

from ostler import markdown, registry
from ostler.finding import Finding
from ostler.links import LinkResolver
from ostler.model import Graph, UINode, read_doc


def _inventory(server: Path, heading: str, resolver: LinkResolver) -> set[Path]:
    """The pages the *server*'s `## <heading>` section links."""
    try:
        doc = read_doc(server)
    except OSError:
        return set()
    section = doc.find_section(heading)
    if section is None:
        return set()
    text = "\n".join(doc.body.split("\n")[section.line_start:section.line_end])
    targets = (resolver.resolve(server, href) for _t, href, _l in markdown.iter_links(text))
    return {t.path.resolve() for t in targets if t is not None and t.file_exists}


def _servers(node: UINode, key: str, resolver: LinkResolver) -> list[Path]:
    hrefs = [href for k, value, _p in node.bullet_order if k == key
             for _t, href, _l in markdown.iter_links(value)]
    targets = (resolver.resolve(node.path, href) for href in hrefs)
    return [t.path.resolve() for t in targets if t is not None and t.file_exists]


def _type_of(path: Path) -> str:
    try:
        return registry.type_of(read_doc(path).frontmatter or {}) or ""
    except OSError:
        return ""


def check_server_membership(graph: Graph, f: list[Finding], resolver: LinkResolver) -> None:
    """Each endpoint page links exactly one server page, and that server's inventory links it back."""
    for uitype in registry.UI_TYPES:
        if uitype.kind != "file" or not uitype.host_page_types:
            continue
        key = uitype.bullet_keys[0].key
        hosts = " or ".join(uitype.host_page_types)
        for node in graph.ui_nodes_of_type(uitype.name):
            if node.kind != "file":
                continue
            servers = [p for p in _servers(node, key, resolver) if _type_of(p) in uitype.host_page_types]
            if len(servers) != 1:
                named = "names none" if not servers else f"names {len(servers)}"
                f.append(Finding(
                    "error", "endpoint-without-server",
                    f"{node.id}: an {uitype.name} page links exactly one {hosts} page from its "
                    f"`{key}:` bullet, and this one {named}. Without it the {uitype.name} has no "
                    f"base URL to be called on and no inventory that finds it. Write "
                    f"`- {key}: [<title>](<{hosts} page>)` under the page's title",
                    path=node.id, line=node.line, ref=key))
                continue
            [server] = servers
            if node.path.resolve() not in _inventory(server, uitype.heading, resolver):
                srel = server.relative_to(graph.root.resolve()).as_posix()
                f.append(Finding(
                    "error", "unlisted-endpoint",
                    f"{node.id}: its {hosts} page {srel} does not link it under "
                    f"`## {uitype.heading}`, so a reader of that page never finds it. Add "
                    f"`- [{node.path.stem}]({node.path.name})` there",
                    path=node.id, line=node.line, ref=srel))
