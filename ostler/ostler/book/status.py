"""What a service answered, in the words of its protocol: an HTTP status number,
a gRPC status code by name or a process exit code. Everything that asks whether an answer is a
success or a refusal asks here, so neither protocol is read as the other."""

from __future__ import annotations

from enum import StrEnum


class Code(StrEnum):
    """The gRPC status codes, in the order of their numbers."""

    OK = "OK"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
    NOT_FOUND = "NOT_FOUND"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    FAILED_PRECONDITION = "FAILED_PRECONDITION"
    ABORTED = "ABORTED"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    UNIMPLEMENTED = "UNIMPLEMENTED"
    INTERNAL = "INTERNAL"
    UNAVAILABLE = "UNAVAILABLE"
    DATA_LOSS = "DATA_LOSS"
    UNAUTHENTICATED = "UNAUTHENTICATED"

    @classmethod
    def numbered(cls, number: int) -> Code:
        return list(cls)[number]


class Exited(int):
    """A process exit code as a status: zero is success, any other number a refusal."""


Status = int | Code | Exited


def succeeded(status: Status) -> bool:
    """The service did what was asked."""
    if isinstance(status, Exited):
        return status == 0
    return status is Code.OK if isinstance(status, Code) else 200 <= status < 300


def refused(status: Status) -> bool:
    """The service turned the call away."""
    if isinstance(status, Exited):
        return status != 0
    return status is not Code.OK if isinstance(status, Code) else status >= 400


def redirected(status: Status) -> bool:
    """The service sent the caller elsewhere instead of answering."""
    return not isinstance(status, (Exited, Code)) and 300 <= status < 400
