"""How an event reaches the service under proof: one role with one way to place an event before the service's
handler, and the judging of the detail an occurrence carries against the event's contract."""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from typing import Any, cast

from ostler.book.errors import BookError
from ostler.book.event import Event


class Delivery:
    """Subclass per way of travelling. `place` puts one event, with the detail of one occurrence, where the
    service's handler will take it, and returns nothing."""

    def place(self, event: type[Event], detail: dict[str, Any]) -> None:
        raise NotImplementedError


class Bus(Delivery):
    """Publishes on a bus that routes to queues, as a person doing QA by hand does: one entry whose source and detail type
    are the event's own. The AWS client comes from `boto3`, an optional extra of the tool, or from the caller."""

    def __init__(self, name: str, endpoint: str = "", region: str = "", client: Any = None) -> None:
        self.name = name
        self.endpoint = endpoint
        self.region = region
        self.client = client

    def place(self, event: type[Event], detail: dict[str, Any]) -> None:
        if self.client is None:
            self.client = self.connect()
        self.client.put_events(Entries=[{"Source": event.source, "DetailType": event.name, "Detail": json.dumps(detail),
                                         "EventBusName": self.name}])

    def connect(self) -> Any:
        try:
            boto3 = importlib.import_module("boto3")
        except ImportError:
            raise BookError(f"publishing on bus {self.name} needs the AWS client: install the aws extra of ostler, "
                            "for example pip install 'ostler[aws]'") from None
        return boto3.client("events", endpoint_url=self.endpoint or None, region_name=self.region or None)


@dataclass(frozen=True)
class Again:
    """A hearing's statement that a second delivery of the same event applies again, with the reason the product does so."""

    reason: str

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise BookError("Again has no reason: say why a second delivery of the same event applies again, for example Again('each delivery adds a line to the trail')")


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
