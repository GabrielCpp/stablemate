from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ostler_qa_diagnostics import DEFAULT_HTTP_TIMEOUT, CheckFailed, HttpError
from ostler_qa_paths import path_steps


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: bytes
    url: str

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        """Parse the body as JSON, naming the URL and a body excerpt when it is not."""
        try:
            return json.loads(self.body)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{self.url} returned {self.status} with a body that is not JSON: "
                f"{self.text[:200]!r}"
            ) from exc


@dataclass(frozen=True)
class Exchange:
    """One request a scenario made, the body it sent, and the status it got back, with no status when it could not connect."""

    method: str
    url: str
    status: int | None
    expected: list[int] | None
    headers: Mapping[str, str]
    body: bytes | None = None


@dataclass(frozen=True)
class ExchangeEvidence:
    """What a failed claim's last request asked and got, which precondition issued its credential, never the credential itself, and the ids it sent that nothing the scenario ran produced."""

    method: str
    path: str
    status: int | None
    expected: list[int] | None
    credential_sent: bool
    precondition: str
    invented: list[str]


@dataclass(frozen=True)
class ClaimFault:
    """The book-fixture fault a claim met: its class, the fixture and the page that declares it."""

    fault_class: str
    fixture: str
    page: str


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Turns a 3xx response into an `HTTPError` instead of following it."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        return None


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirectHandler)


class Http:
    """A small stdlib HTTP client bound to a target's `base_url`."""

    def __init__(
        self,
        base_url: str | None,
        *,
        timeout: float = DEFAULT_HTTP_TIMEOUT,
        on_unexpected_status: Callable[[str, str, int, Sequence[int], str], None] | None = None,
        on_exchange: Callable[[Exchange], None] | None = None,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.timeout = timeout
        self.headers: dict[str, str] = {}
        self._on_unexpected_status = on_unexpected_status
        self._on_exchange = on_exchange

    def url_for(self, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        if not self.base_url:
            raise ValueError(
                f"{path!r} is relative but the target declares no base_url; pass an "
                "absolute URL or set base_url= on the target"
            )
        return f"{self.base_url}/{path.lstrip('/')}"

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        data: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        expect_status: int | Sequence[int] | None = None,
        timeout: float | None = None,
        follow_redirects: bool = True,
    ) -> Response:
        url = self.url_for(path)
        merged = {**self.headers, **(headers or {})}
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            merged.setdefault("Content-Type", "application/json")
        request = urllib.request.Request(url, data=data, method=method.upper())  # noqa: S310
        for key, value in merged.items():
            request.add_header(key, value)
        opener_open = _NO_REDIRECT_OPENER.open if not follow_redirects else urllib.request.urlopen
        allowed = _allowed_statuses(expect_status)
        expected = sorted(allowed) if allowed is not None else None
        try:
            with opener_open(  # noqa: S310
                request, timeout=timeout or self.timeout
            ) as raw:
                response = Response(raw.status, dict(raw.headers), raw.read(), url)
        except urllib.error.HTTPError as exc:
            response = Response(exc.code, dict(exc.headers or {}), exc.read(), url)
        except urllib.error.URLError as exc:
            self._exchanged(Exchange(method.upper(), url, None, expected, merged, data))
            raise HttpError(f"{method.upper()} {url} could not connect: {exc.reason}") from exc
        self._exchanged(Exchange(method.upper(), url, response.status, expected, merged, data))
        if allowed is None:
            if response.status >= 400:
                raise HttpError(
                    f"{method.upper()} {url} returned {response.status}: {response.text[:500]}"
                )
        elif response.status not in allowed:
            if self._on_unexpected_status is not None:
                self._on_unexpected_status(method.upper(), url, response.status, sorted(allowed), response.text)
            raise HttpError(
                f"{method.upper()} {url} returned {response.status}, expected "
                f"{sorted(allowed)}: {response.text[:500]}",
                recorded=self._on_unexpected_status is not None,
            )
        return response

    def _exchanged(self, exchange: Exchange) -> None:
        if self._on_exchange is not None:
            self._on_exchange(exchange)

    def get(self, path: str, **kwargs: Any) -> Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Response:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Response:
        return self.request("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> Response:
        return self.request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Response:
        return self.request("DELETE", path, **kwargs)

    def head(self, path: str, **kwargs: Any) -> Response:
        return self.request("HEAD", path, **kwargs)

    def options(self, path: str, **kwargs: Any) -> Response:
        return self.request("OPTIONS", path, **kwargs)


def _allowed_statuses(expect_status: int | Sequence[int] | None) -> set[int] | None:
    if expect_status is None:
        return None
    if isinstance(expect_status, int):
        return {expect_status}
    return set(expect_status)


def _not_yet(exc: BaseException) -> bool:
    """Does this exception mean "the page has not got there yet", or "the plan is wrong"?"""
    if isinstance(exc, CheckFailed):
        return False
    return isinstance(exc, (TimeoutError, AssertionError)) or type(exc).__module__.split(".")[
        0
    ] == "playwright"


def _sampled(actual: Any) -> Any:
    """Read an `actual=` that may be a callable, after the poll loop has settled."""
    if not callable(actual):
        return actual
    try:
        return actual()
    except BaseException as exc:  # noqa: BLE001 — evidence, not a verdict
        return repr(exc)


def _unsatisfiable_http_status(args: Mapping[str, Any]) -> str:
    """Why no response can satisfy this call, or empty when one can."""
    if "path" not in args:
        return ""
    route = str(args["path"])
    path = route.partition("?")[0]
    if urllib.parse.urlsplit(f"http://host{path}").path == path:
        return ""
    return (f"path={route!r} can never be the route that answered: this check reads the path "
            "component of the request URL, and a `#` fragment never reaches the server")


def _unsatisfiable_json_path(args: Mapping[str, Any]) -> str:
    """Why no document can satisfy this call, or empty when one can."""
    path = str(args["path"])
    if "absent" in args and bool(args["absent"]) and not path_steps(path):
        return (f"path={path!r} names the whole document, and every observation has one, "
                "so `absent=true` can never hold")
    return ""


def _unsatisfiable_omits(args: Mapping[str, Any]) -> str:
    """Why no subject can satisfy this call, or empty when one can."""
    if "matches" not in args:
        return ""
    pattern = str(args["matches"])
    try:
        compiled = re.compile(pattern)
    except re.error as err:
        return f"/{pattern}/ is not a pattern this check can read: {err}"
    if compiled.search("") is None:
        return ""
    return (f"/{pattern}/ matches the empty subject, so it matches every subject and nothing "
            "can be omitted from one")


def _unsatisfiable_text_pattern(args: Mapping[str, Any]) -> str:
    """Why no text can satisfy this call's `matches=`, or empty when one can."""
    if "matches" not in args:
        return ""
    pattern = str(args["matches"])
    try:
        _ = re.compile(pattern)
    except re.error as err:
        return f"/{pattern}/ is not a pattern this check can read: {err}"
    return ""


UNSATISFIABLE: dict[str, Callable[[Mapping[str, Any]], str]] = {
    "http_status": _unsatisfiable_http_status,
    "response_header": _unsatisfiable_text_pattern,
    "json_path": _unsatisfiable_json_path,
    "omits": _unsatisfiable_omits,
    "stdout": _unsatisfiable_text_pattern,
    "stderr": _unsatisfiable_text_pattern,
    "contents": _unsatisfiable_text_pattern,
}
