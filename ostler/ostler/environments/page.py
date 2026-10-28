"""An environment page's `variables:` bullet: the literals a command may read and the names saddlebag holds."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ostler import markdown
from ostler.ids import resolve
from ostler.markdown import bullet_text, children
from ostler.model import Graph, UINode

HELD_MARK = "secret"
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class VariableError(ValueError):
    """A `variables:` child that cannot be read as a name and a value."""

    def __init__(self, message: str, name: str = "") -> None:
        super().__init__(message)
        self.name = name


@dataclass(frozen=True)
class Variables:
    """The page's variables in page order: a literal carries its value, a held name carries `None`."""

    entries: tuple[tuple[str, str | None], ...] = ()

    @property
    def literals(self) -> dict[str, str]:
        return {name: value for name, value in self.entries if value is not None}

    @property
    def held(self) -> frozenset[str]:
        return frozenset(name for name, value in self.entries if value is None)


def slug_of(node: UINode) -> str:
    """The page's `slug`, or its file name without the extension."""
    return str(node.data.get("slug") or node.path.stem)


def read_variables(node: UINode) -> Variables:
    """The `variables:` children of the `environment` node *node*."""
    entries: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    for item in children(node.meta, "variables"):
        idx = markdown.label_colon_index(item)
        if idx == -1:
            raise VariableError(f"`{item}` has no `NAME: value` form", item)
        name = item[:idx].strip().strip("`")
        if not _NAME.fullmatch(name):
            raise VariableError(f"`{name}` is not a valid environment variable name", name)
        if name in seen:
            raise VariableError(f"`{name}` is listed twice", name)
        seen.add(name)
        value = bullet_text(item[idx + 1:])
        entries.append((name, None if value == HELD_MARK else value))
    return Variables(tuple(entries))


def find_environment(graph: Graph, token: str) -> UINode:
    """The `environment` page *token* names by id, handle or slug."""
    node = graph.find_ui_node(resolve(graph, token))
    if node is None:
        node = next((n for n in graph.ui_nodes_of_type("environment") if slug_of(n) == token), None)
    if node is None:
        raise LookupError(f"no environment page is named `{token}`")
    if node.type != "environment":
        raise LookupError(f"`{token}` is a {node.type} page, not an environment")
    return node
