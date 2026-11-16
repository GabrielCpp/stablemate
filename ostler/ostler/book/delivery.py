"""How an event reaches the service under proof: one role with one way to place an event before the service's
handler, and the judging of the detail an occurrence carries against the event's contract."""

from __future__ import annotations

import importlib
import json
import uuid
from dataclasses import dataclass
from typing import Any, cast

from ostler.book.errors import BookError
from ostler.book.event import Event


class Delivery:
    """Subclass per way of travelling. `place` puts one event, with the detail of one occurrence, where the
    service's handler will take it, and returns nothing. The way that places events also taps them: `open_tap` starts
    reading every event the environment carries, `tapped` returns the name and decoded detail of the events read since
    the last call, and `close_tap` removes what `open_tap` made. A way that cannot tap raises NotImplementedError."""

    def place(self, event: type[Event], detail: dict[str, Any]) -> None:
        raise NotImplementedError

    def open_tap(self) -> None:
        raise NotImplementedError(f"{type(self).__name__} cannot tap the events of the environment")

    def tapped(self) -> list[tuple[str, dict[str, Any]]]:
        raise NotImplementedError(f"{type(self).__name__} cannot tap the events of the environment")

    def close_tap(self) -> None:
        raise NotImplementedError(f"{type(self).__name__} cannot tap the events of the environment")


class Bus(Delivery):
    """Publishes on a bus that routes to queues, as a person doing QA by hand does: one entry whose source and detail type
    are the event's own. It taps the bus with a queue the run makes for itself and a rule that sends every event of the bus
    to it, both removed when the tap closes. The AWS clients come from `boto3`, an optional extra of the tool, or from the
    caller: `client` for the bus, `queues` for the queue service."""

    def __init__(self, name: str, endpoint: str = "", region: str = "", client: Any = None, queues: Any = None) -> None:
        self.name = name
        self.endpoint = endpoint
        self.region = region
        self.client = client
        self.queues = queues
        self.tap_name = ""
        self.tap_url = ""
        self.tap_rule = False
        self.tap_target = False

    def place(self, event: type[Event], detail: dict[str, Any]) -> None:
        if self.client is None:
            self.client = self.connect()
        self.client.put_events(Entries=[{"Source": event.source, "DetailType": event.name, "Detail": json.dumps(detail),
                                         "EventBusName": self.name}])

    def connect(self, service: str = "events") -> Any:
        try:
            boto3 = importlib.import_module("boto3")
        except ImportError:
            raise BookError(f"publishing on bus {self.name} needs the AWS client: install the aws extra of ostler, "
                            "for example pip install 'ostler[aws]'") from None
        return boto3.client(service, endpoint_url=self.endpoint or None, region_name=self.region or None)

    def open_tap(self) -> None:
        if self.client is None:
            self.client = self.connect()
        if self.queues is None:
            self.queues = self.connect("sqs")
        self.tap_name = f"ostler-tap-{uuid.uuid4().hex[:8]}"
        try:
            self.tap_url = self.queues.create_queue(QueueName=self.tap_name)["QueueUrl"]
            arn = self.queues.get_queue_attributes(QueueUrl=self.tap_url, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
            rule = self.client.put_rule(Name=self.tap_name, EventBusName=self.name, State="ENABLED",
                                        EventPattern=json.dumps({"source": [{"prefix": ""}]}))
            self.tap_rule = True
            policy = {"Version": "2012-10-17", "Statement": [{
                "Effect": "Allow", "Principal": {"Service": "events.amazonaws.com"}, "Action": "sqs:SendMessage", "Resource": arn,
                "Condition": {"ArnEquals": {"aws:SourceArn": rule["RuleArn"]}}}]}
            self.queues.set_queue_attributes(QueueUrl=self.tap_url, Attributes={"Policy": json.dumps(policy)})
            self.tap_target = True
            self.client.put_targets(Rule=self.tap_name, EventBusName=self.name, Targets=[{"Id": "tap", "Arn": arn}])
        except BaseException:
            self.close_tap()
            raise

    def tapped(self) -> list[tuple[str, dict[str, Any]]]:
        got = self.queues.receive_message(QueueUrl=self.tap_url, MaxNumberOfMessages=10, WaitTimeSeconds=0)
        out: list[tuple[str, dict[str, Any]]] = []
        for message in got.get("Messages", []):
            self.queues.delete_message(QueueUrl=self.tap_url, ReceiptHandle=message["ReceiptHandle"])
            envelope = json.loads(message["Body"])
            detail = envelope.get("detail", {})
            out.append((str(envelope.get("detail-type", "")), json.loads(detail) if isinstance(detail, str) else detail))
        return out

    def close_tap(self) -> None:
        if self.tap_target:
            self.client.remove_targets(Rule=self.tap_name, EventBusName=self.name, Ids=["tap"])
            self.tap_target = False
        if self.tap_rule:
            self.client.delete_rule(Name=self.tap_name, EventBusName=self.name)
            self.tap_rule = False
        if self.tap_url:
            self.queues.delete_queue(QueueUrl=self.tap_url)
            self.tap_url = ""


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
