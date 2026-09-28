"""Where the book's one-to-one mapping from node to Playwright locator breaks, one class per way."""

from __future__ import annotations

from dataclasses import dataclass

from ostler.untyped import JsonValue


@dataclass(frozen=True, slots=True)
class LocatorCollision:
    """Nodes on one screen that one role and one accessible name cannot tell apart."""

    screen: str
    role: str
    name: str
    nodes: tuple[str, ...]
    template: str = ""

    def ref(self, node_id: str) -> str:
        """The address of this collision as *node_id* takes part in it, not of the node."""
        others = "+".join(sorted(o.rpartition("#")[2] for o in self.nodes if o != node_id))
        return f"{node_id}#" + ":".join((self.screen, self.role, self.name, others))

    def row(self) -> dict[str, JsonValue]:
        row: dict[str, JsonValue] = {"screen": self.screen, "role": self.role, "name": self.name}
        if self.template:
            row["template"] = self.template
        row["nodes"] = list(self.nodes)
        return row


@dataclass(frozen=True, slots=True)
class InvalidRole:
    """A node whose ``role:`` is not an ARIA role."""

    screen: str
    node: str
    role: str

    def row(self) -> dict[str, JsonValue]:
        return {"screen": self.screen, "node": self.node, "role": self.role}


@dataclass(frozen=True, slots=True)
class StaticTemplate:
    """A repeated node whose name carries no datum of the collection it iterates."""

    screen: str
    node: str
    template: str
    iterates: str

    def row(self) -> dict[str, JsonValue]:
        return {"screen": self.screen, "node": self.node, "template": self.template,
                "iterates": self.iterates}


@dataclass(frozen=True, slots=True)
class UnprovenUniqueName:
    """A repeated node told apart only by display values nothing guarantees distinct."""

    screen: str
    node: str
    template: str
    binds: tuple[str, ...]

    def row(self) -> dict[str, JsonValue]:
        return {"screen": self.screen, "node": self.node, "template": self.template,
                "binds": list(self.binds)}


@dataclass(frozen=True, slots=True)
class MalformedTemplate:
    """A repeated-scope node whose name template has an unbalanced brace."""

    screen: str
    node: str
    template: str

    def row(self) -> dict[str, JsonValue]:
        return {"screen": self.screen, "node": self.node, "template": self.template}


@dataclass(frozen=True, slots=True)
class TemplateOutsideRepeat:
    """A node whose name reads as a template but which repeats over nothing."""

    screen: str
    node: str
    template: str

    def row(self) -> dict[str, JsonValue]:
        return {"screen": self.screen, "node": self.node, "template": self.template}


@dataclass(frozen=True, slots=True)
class InvalidVariants:
    """A repeated node whose ``variants:`` value the micro-syntax rejects."""

    screen: str
    node: str
    value: str

    def row(self) -> dict[str, JsonValue]:
        return {"screen": self.screen, "node": self.node, "value": self.value}


@dataclass(frozen=True, slots=True)
class UnnamedInteractive:
    """An operable control with no accessible name."""

    screen: str
    node: str
    role: str

    def row(self) -> dict[str, JsonValue]:
        return {"screen": self.screen, "node": self.node, "role": self.role}
