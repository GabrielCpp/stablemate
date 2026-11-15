"""How an event reaches the service under proof: one role with one way to place an event before the service's
handler, and the judging of the detail an occurrence carries against the event's contract."""

from __future__ import annotations

from typing import Any, cast

from ostler.book.event import Event


class Delivery:
    """Subclass per way of travelling. `place` puts one event, with the detail of one occurrence, where the
    service's handler will take it, and returns nothing."""

    def place(self, event: type[Event], detail: dict[str, Any]) -> None:
        raise NotImplementedError


def found(value: object, path: str) -> bool:
    """Whether a path of the detail, going through lists as `lines[].quantity` and maps as `by{}.name`, leads to a value."""
    if not path:
        return True
    head, _, rest = path.partition(".")
    name, many = (head[:-2], "[]") if head.endswith("[]") else (head[:-2], "{}") if head.endswith("{}") else (head, "")
    if not isinstance(value, dict) or name not in value:
        return False
    inner = cast("dict[str, object]", value)[name]
    if many == "[]":
        return isinstance(inner, list) and any(found(item, rest) for item in inner)
    if many == "{}":
        return isinstance(inner, dict) and any(found(item, rest) for item in cast("dict[str, object]", inner).values())
    return found(inner, rest)


def faults(event: type[Event], detail: object, reads: tuple[str, ...]) -> list[str]:
    """What the detail of one occurrence gets wrong against the contract of its event, and every path the hearing
    reads that it does not carry."""
    assert event.detail is not None
    out = event.detail.check(detail, "detail")
    out += [f"detail.{path}: the hearing reads it and the detail does not carry it" for path in reads if not found(detail, path)]
    return out
