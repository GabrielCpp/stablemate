"""The tap an environment gives an event run: what a run has seen of how long events take to land, the events read
off the tap, and the proof that an action's emissions arrived."""

from __future__ import annotations

import atexit
import signal
from typing import Any, Iterable, cast

from ostler.book.delivery import Delivery
from ostler.book.event import Event
from ostler.book.http import Id, Identities, List, Object, Shape, canonical

RETAKES = 1000
PATIENCE = 50


def ownership(shape: Shape | None, value: object, ids: Identities) -> tuple[int, int]:
    """How many ids of a detail the run made, and how many it did not."""
    if isinstance(shape, Id):
        if value is None:
            return 0, 0
        return (1, 0) if ids.model_of(shape.kind, str(value)) is not None else (0, 1)
    if isinstance(shape, List) and isinstance(value, list):
        counts = [ownership(shape.of, item, ids) for item in value]
        return sum(c[0] for c in counts), sum(c[1] for c in counts)
    if isinstance(shape, Object) and isinstance(value, dict):
        counts = [ownership(spec.shape, value.get(name), ids) for name, spec in shape.fields.items()]
        return sum(c[0] for c in counts), sum(c[1] for c in counts)
    return 0, 0


def plain(value: object) -> object:
    if isinstance(value, dict):
        return {k: plain(v) for k, v in cast("dict[str, object]", value).items()}
    if isinstance(value, (list, tuple)):
        return tuple(plain(v) for v in cast("Iterable[object]", value))
    return value


def differences(want: dict[str, Any], got: object, where: str = "") -> list[str]:
    """Each path the book predicts whose value the tapped detail does not hold, with both values."""
    out: list[str] = []
    for name, expected in want.items():
        path = f"{where}.{name}" if where else name
        held = cast("dict[str, object]", got).get(name) if isinstance(got, dict) else None
        if isinstance(expected, dict):
            out += differences(cast("dict[str, Any]", expected), held, path)
        elif plain(expected) != plain(held):
            out.append(f"{path} tapped {held!r}, the book says {expected!r}")
    return out


class Landings:
    """What this run has seen of how long an event takes to land: the most
    reads one took, and whether one never landed."""

    longest = 0
    missed = False

    @classmethod
    def bound(cls) -> int:
        """How many reads the next event gets. Until an event fails to land,
        every one gets `RETAKES`. After that the run is red already, and an
        event gets three times the longest landing seen, so the cells behind a
        broken consumer fail in seconds each."""
        return max(3 * cls.longest, PATIENCE) if cls.missed else RETAKES


class Deliveries:
    """The way events reach the service in this run, as the environment names it. Class state, like `Landings`: a
    run is one process."""

    role: Delivery | None = None
    delivered = 0
    declared = 0
    failed = 0
    proven = 0
    failed_emissions = 0
    unproven = 0
    tapping = False
    cannot = False
    buffer: list[tuple[str, Any]] = []
    hooked = False
    handler: Any = None

    @classmethod
    def begin(cls, role: Delivery | None) -> None:
        cls.close()
        cls.role = role
        cls.delivered = cls.declared = cls.failed = 0
        cls.proven = cls.failed_emissions = cls.unproven = 0
        cls.cannot = False
        cls.buffer = []

    @classmethod
    def watch(cls) -> None:
        """Opens the tap the first time an action that emits is about to be taken. An environment that names no delivery,
        or one that cannot tap, leaves the emissions unproven."""
        if cls.tapping or cls.cannot or cls.role is None:
            return
        try:
            cls.role.open_tap()
        except NotImplementedError:
            cls.cannot = True
            return
        cls.tapping = True
        if not cls.hooked:
            atexit.register(cls.close)
            cls.hooked = True
        try:
            cls.handler = signal.signal(signal.SIGTERM, cls.terminated)
        except ValueError:
            cls.handler = None

    @staticmethod
    def terminated(signum: int, frame: object) -> None:
        raise SystemExit(128 + signum)

    @classmethod
    def close(cls) -> None:
        """Removes what the tap made. Safe to call when no tap is open."""
        if not cls.tapping:
            return
        cls.tapping = False
        if cls.handler is not None:
            signal.signal(signal.SIGTERM, cls.handler)
            cls.handler = None
        if cls.role is not None:
            cls.role.close_tap()

    @classmethod
    def prove(cls, event: type[Event], wanted: dict[str, Any], ids: Identities, name: str) -> str:
        """Reads the tap again, at most `Landings.bound()` times, until an event of this name about a record the run made
        agrees with what the action announces. The events about the run's records that matched nothing stay buffered."""
        assert cls.role is not None and event.detail is not None
        most = Landings.bound()
        off: list[str] = []
        for reads in range(1, most + 1):
            for tapped, detail in cls.role.tapped():
                owned, strange = ownership(event.detail, detail, ids)
                if owned or not strange:
                    cls.buffer.append((tapped, canonical(event.detail, detail, app=True, ids=ids, where=event.name)))
            off = []
            for position, (tapped, seen) in enumerate(cls.buffer):
                if tapped != event.name:
                    continue
                off = differences(wanted, seen)
                if not off:
                    del cls.buffer[position]
                    Landings.longest = max(Landings.longest, reads)
                    return ""
        Landings.missed = True
        if not off:
            return f"{name} should emit {event.name} about a record this run made; the tap read none in {most} reads"
        return f"{name} emitted {event.name} but it disagrees with the book: " + "; ".join(off)

    @classmethod
    def line(cls) -> str:
        """The run's second deliveries and emissions, or nothing when no hearing was delivered and no action emitted."""
        lines = []
        if cls.delivered:
            lines.append(f"repeats: {cls.delivered} delivered, {cls.declared} applied again as declared, {cls.failed} fail")
        if cls.proven or cls.failed_emissions or cls.unproven:
            lines.append(f"emissions: {cls.proven} proven, {cls.failed_emissions} fail, {cls.unproven} unproven")
        return "\n".join(lines)
