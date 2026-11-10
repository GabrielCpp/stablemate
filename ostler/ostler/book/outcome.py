"""What an observer sees after a step: the answer, and the rows now listed.
What a row is belongs to the service; ostler compares them with == and prints
them with str()."""

from dataclasses import dataclass, field
from typing import Any

from ostler.book.status import Status


@dataclass(frozen=True)
class Done:
    """`view` is what the answer carried: the record a write made or changed, the
    rows a read found, the values a read showed."""

    rows: tuple[object, ...] = ()
    view: tuple[object, ...] | None = field(default=None, compare=False)

    def __str__(self) -> str:
        return "ok"


@dataclass(frozen=True)
class Refusal:
    message: str
    status: Status = 400

    def __str__(self) -> str:
        return f"refused {self.status} {self.message}"


@dataclass(frozen=True)
class Refusals:
    """The refusals a service gives a whole class of wrong input, when the model
    has no rule of its own for the input: an id that is not an id, one that
    names nothing, one that names a record of another kind, a field left out,
    a body field of the wrong type. A wrong type falls back to the malformed
    refusal when none is declared for it."""

    malformed: Refusal | None = None
    unknown_id: Refusal | None = None
    wrong_kind: Refusal | None = None
    missing: Refusal | None = None
    wrong_type: Refusal | None = None

    def over(self, base: "Refusals") -> "Refusals":
        """These refusals, and the base's where these name none."""
        return Refusals(self.malformed or base.malformed, self.unknown_id or base.unknown_id,
                        self.wrong_kind or base.wrong_kind, self.missing or base.missing,
                        self.wrong_type or base.wrong_type)

    def of(self, kind: str) -> Refusal | None:
        if kind == "wrong_type":
            return self.wrong_type or self.malformed
        return getattr(self, kind)


@dataclass(frozen=True)
class Unreachable:
    """The surface offers no way to attempt this step: the mistake the model
    refuses cannot be made here."""

    reason: str

    def __str__(self) -> str:
        return f"unreachable: {self.reason}"


@dataclass(frozen=True)
class Flawed:
    """A known defect shows for this call: the app answers the defect's status
    and message and makes the defect's change, if any. `meant` is what the
    model would have answered, `reduced` the change it would have made, `wrong`
    the change the app makes instead."""

    defect: Any
    meant: "Done | Refusal"
    reduced: Any = field(default=None, compare=False)
    wrong: Any = field(default=None, compare=False)

    def __str__(self) -> str:
        return f"defect {self.defect.status} {self.defect.message}"


class CannotReach(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


Outcome = Done | Refusal | Unreachable | Flawed
