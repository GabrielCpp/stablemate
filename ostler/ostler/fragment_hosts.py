"""`ostler doctor`'s check that every fragment page names one host page that is no fragment, and that host links it."""

from __future__ import annotations

from pathlib import Path

from ostler import markdown, registry
from ostler.finding import Finding
from ostler.links import LinkResolver
from ostler.model import Graph, UINode, fragment_host, read_doc


def _hosts(node: UINode, resolver: LinkResolver) -> list[Path]:
    hrefs = [href for k, value, _p in node.bullet_order if k == "host"
             for _t, href, _l in markdown.iter_links(value)]
    targets = (resolver.resolve(node.path, href) for href in hrefs)
    return [t.path.resolve() for t in targets if t is not None and t.file_exists]


def _links(host: Path, fragment: Path, resolver: LinkResolver) -> bool:
    try:
        body = read_doc(host).body
    except OSError:
        return False
    targets = (resolver.resolve(host, href) for _t, href, _l in markdown.iter_links(body))
    return any(t is not None and t.file_exists and t.path.resolve() == fragment for t in targets)


def host_type(graph: Graph, rel: str) -> str:
    """The type of the page the fragment at *rel* continues, or `fragment` when it names none."""
    node = next((n for n in graph.ui_nodes if n.id == rel and n.kind == "file"), None)
    host = fragment_host(node, graph.root) if node is not None else ""
    if not host:
        return "fragment"
    try:
        return registry.type_of(read_doc(graph.root / host).frontmatter or {}) or "fragment"
    except OSError:
        return "fragment"


def check_fragment_hosts(graph: Graph, f: list[Finding], resolver: LinkResolver) -> None:
    """Each fragment page links exactly one host page from its `host:` bullet, that host is no fragment, and it links the fragment back."""
    root = graph.root.resolve()
    for node in graph.ui_nodes_of_type("fragment"):
        if node.kind != "file" or "host" not in node.meta:
            continue
        hosts = _hosts(node, resolver)
        if len(hosts) != 1:
            named = "names no page" if not hosts else f"names {len(hosts)} pages"
            f.append(Finding(
                "error", "fragment-without-host",
                f"{node.id}: a fragment continues exactly one host page, and its `host:` bullet "
                f"{named}. Its sections are read under the host's rules, so without one they "
                f"belong to no page. Write `- host: [<title>](<host page>)` under the page's title",
                path=node.id, line=node.line, ref="host"))
            continue
        [host] = hosts
        hrel = host.relative_to(root).as_posix()
        if registry.type_of(read_doc(host).frontmatter or {}) == "fragment":
            f.append(Finding(
                "error", "fragment-of-fragment",
                f"{node.id}: its host {hrel} is itself a fragment, so its sections have no page "
                f"whose rules they follow. Point `host:` at the page {hrel} continues",
                path=node.id, line=node.line, ref=hrel))
        elif not _links(host, node.path.resolve(), resolver):
            f.append(Finding(
                "error", "unlisted-fragment",
                f"{node.id}: its host {hrel} does not link it, so a reader of the host never "
                f"finds the sections it continues. Add `- [{node.path.stem}]({node.path.name})` "
                f"to {hrel} where those sections left",
                path=node.id, line=node.line, ref=hrel))
