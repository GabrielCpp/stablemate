"""Which links of a flow's `steps:` a journey performs, and which only say where it is or what it reaches.

A step bullet often names the control a reader uses beside the screen it sits on, the panel it
mounts or the field and endpoint its request reaches. Only the control is performed. The other
links are context: a walker performs none of them, and a journey that counted them as steps
would be refused for a place it never had to visit, or bound to two services when its page
alone talks to the second.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ostler import markdown
from ostler.untyped import JsonValue

if TYPE_CHECKING:
    from ostler.qa.obligation_frame import BookNode

PERFORMED_TYPES = frozenset({"interaction", "invocation", "endpoint", "command"})
PLACE_TYPES = frozenset({"screen", "component", "field"})


@dataclass(frozen=True, slots=True)
class JourneyStep:
    """One node a flow's `steps:` names: its id, the link the book wrote, its type and its surface."""

    ref: str
    href: str
    node_type: str
    surface: str

    def row(self) -> dict[str, JsonValue]:
        """The step as the obligation row carries it."""
        return {"ref": self.ref, "href": self.href, "nodeType": self.node_type, "surface": self.surface}


def _bullet_steps(item: str, resolved: Mapping[str, str], book: Mapping[str, BookNode]) -> list[JourneyStep]:
    """Every link one `steps:` bullet writes, resolved to the node it names."""
    steps: list[JourneyStep] = []
    for _text, href in markdown.extract_refs(item).links:
        target_id = resolved.get(href, "")
        target = book.get(target_id) if target_id else None
        steps.append(JourneyStep(ref=target_id, href=href, node_type=target.type if target else "",
                                 surface=target.surface if target else ""))
    return steps


def _performed_in(steps: list[JourneyStep]) -> list[JourneyStep]:
    """The links of one bullet a walker performs: its actions when it names one, else all but its places."""
    if any(step.node_type in PERFORMED_TYPES for step in steps):
        return [step for step in steps if not step.ref or step.node_type in PERFORMED_TYPES]
    return [step for step in steps if step.node_type not in PLACE_TYPES]


def _called_endpoints(steps: list[JourneyStep], book: Mapping[str, BookNode]) -> set[str]:
    """The endpoints the journey's invocations name in their `on:`, which their own requests reach."""
    return {target.id for step in steps if step.node_type == "invocation" and step.ref in book
            for target in book[step.ref].targets("on", book) if target.type == "endpoint"}


def journey_steps(node: BookNode, book: Mapping[str, BookNode]) -> tuple[JourneyStep, ...]:
    """The nodes a flow's `steps:` performs, in the order the book wrote them."""
    resolved = {edge.href: edge.to for edge in node.edges if edge.to and edge.href}
    walk = [step for item in node.bullets.get("steps", ()) for step in _performed_in(_bullet_steps(item, resolved, book))]
    called = _called_endpoints(walk, book)
    return tuple(step for step in walk if not (step.node_type == "endpoint" and step.ref in called))


__all__ = ["PERFORMED_TYPES", "PLACE_TYPES", "JourneyStep", "journey_steps"]
