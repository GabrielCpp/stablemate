"""The verifiers that observe what a request or a command answered: its status, its headers, its exit code and what it printed."""

from __future__ import annotations

import re
import urllib.parse
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from ostler_qa_paths import JsonValue
from ostler_qa_verdicts import Args, Verdict, json_value, str_arg, verdict


@dataclass(frozen=True)
class HttpReading:
    """What a response answered: its status, its parsed body, and the route that answered."""

    status: int
    body: JsonValue
    route: str | None


def read_response(observed: object, args: Args) -> HttpReading:
    """The status code, parsed body and route of whatever a scenario handed over as a response."""
    if isinstance(observed, int) and not isinstance(observed, bool):
        status: object = observed
    else:
        status = getattr(observed, "status", getattr(observed, "status_code", None))
    if not isinstance(status, int):
        raise TypeError(
            "http_status observes a response — pass the object qa.http returned (or its "
            f"integer status), not {type(observed).__name__}"
        )
    body: JsonValue = None
    reader = getattr(observed, "json", None)
    if callable(reader):
        try:
            body = json_value(reader())
        except ValueError:
            body = None
    url = getattr(observed, "url", None)
    if "path" in args and not isinstance(url, str):
        raise TypeError(
            "http_status(path=…) observes which request answered — pass the object "
            f"qa.http returned, not {type(observed).__name__}"
        )
    route = urllib.parse.urlsplit(url).path if isinstance(url, str) else None
    return HttpReading(status=status, body=body, route=route)


def verify_http_status(reading: HttpReading, args: Args) -> Verdict:
    expected: dict[str, object] = {"code": args["code"]}
    actual: dict[str, object] = {"code": reading.status}
    passed = reading.status == args["code"]
    if "title" in args:
        found = reading.body.get("title") if isinstance(reading.body, dict) else None
        expected["title"], actual["title"] = args["title"], found
        passed = passed and found == args["title"]
    if "path" in args:
        expected["path"], actual["path"] = str_arg(args, "path"), reading.route
        passed = passed and reading.route == str_arg(args, "path")
    return verdict(passed, actual, expected)


def verify_conflict_on_stale(reading: HttpReading, args: Args) -> Verdict:
    return verdict(400 <= reading.status < 500, reading.status, "a refusal (4xx)")


@dataclass(frozen=True)
class HeaderReading:
    """The headers a response carried, in the order it carried them."""

    headers: tuple[tuple[str, str], ...]


def read_headers(observed: object, args: Args) -> HeaderReading:
    headers = getattr(observed, "headers", None)
    if callable(headers):
        headers = headers()
    if not isinstance(headers, Mapping):
        raise TypeError(
            "response_header observes the headers a response carried — pass the object "
            f"qa.http returned, not {type(observed).__name__}"
        )
    return HeaderReading(headers=tuple((str(key), str(value)) for key, value in headers.items()))


def verify_response_header(reading: HeaderReading, args: Args) -> Verdict:
    wanted = str(str_arg(args, "name")).lower()
    value = next((v for k, v in reading.headers if k.lower() == wanted), None)
    actual = {str_arg(args, "name"): value}
    if value is None:
        return verdict(False, actual, {str_arg(args, "name"): "present"})
    if "equals" in args:
        return verdict(value == args["equals"], actual, {str_arg(args, "name"): args["equals"]})
    return verdict(re.search(str_arg(args, "matches"), value) is not None, actual,
                    {str_arg(args, "name"): f"~ {str_arg(args, 'matches')}"})


@dataclass(frozen=True)
class ExitReading:
    """The code a process exited with."""

    code: int


def read_exit(observed: object, args: Args) -> ExitReading:
    code = getattr(observed, "exit_code", None)
    if isinstance(code, bool) or not isinstance(code, int):
        raise TypeError(
            "exit_status observes a tool or maestro result (something with an exit_code), "
            f"got {type(observed).__name__}"
        )
    return ExitReading(code=code)


def verify_exit_status(reading: ExitReading, args: Args) -> Verdict:
    """The process ended the way the book says it does."""
    return verdict(reading.code == args["code"], reading.code, args["code"])


@dataclass(frozen=True)
class StreamReading:
    """What a command printed on one output stream."""

    printed: str


def read_stream(stream: str) -> Callable[[object, Args], StreamReading]:
    def read(observed: object, args: Args) -> StreamReading:
        printed = getattr(observed, stream, None)
        if not isinstance(printed, str):
            raise TypeError(
                f"{stream} observes a tool result (something with a text {stream}), "
                f"got {type(observed).__name__}"
            )
        return StreamReading(printed=printed)

    return read


def verify_printed(reading: StreamReading, args: Args) -> Verdict:
    """The command printed on the stream what the book says it prints."""
    missing = {key: args[key] for key in ("text", "matches") if key in args}
    if "text" in args and str_arg(args, "text") in reading.printed:
        missing.pop("text")
    if "matches" in args and re.search(str_arg(args, "matches"), reading.printed) is not None:
        missing.pop("matches")
    return verdict(not missing, reading.printed, missing)
