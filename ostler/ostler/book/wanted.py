"""How a book names the requests and answers a page's behaviour is waited on by."""

from __future__ import annotations

import re
from typing import Any, Callable
from urllib.parse import parse_qsl, urlsplit

from ostler.book.pagedata import on_route

Wanted = Callable[[Any], bool]


def request(method: str, path: str, **query: str) -> Wanted:
    """Matches a request by verb, path (`/todos` also matches `/todos/{id}`, and a `{name}` in the path stands for
    one segment, as in `/projects/{id}/variants`) and the query parameters named; a parameter not sent counts as ''."""
    shape = "/".join("[^/]+" if re.fullmatch(r"\{[^{}/]+\}", part) else re.escape(part) for part in path.split("/"))
    template = re.compile(f"{shape}(/.*)?")

    def wanted(req: Any) -> bool:
        parts = urlsplit(req.url)
        on_path = template.fullmatch(parts.path) is not None
        params = dict(parse_qsl(parts.query, keep_blank_values=True))
        return req.method == method and on_path and all(params.get(k, "") == v for k, v in query.items())

    setattr(wanted, "text", " ".join([method, path, *(f"{k}={v}" for k, v in query.items())]))
    return wanted


def asked(thing: Any) -> Any:
    return getattr(thing, "request", thing)


def answer(method: str, path: str, **query: str) -> Wanted:
    """Matches the answer to such a request, whatever its status."""
    wanted = request(method, path, **query)
    return lambda response: wanted(asked(response))


def action(route: str, name: str) -> Wanted:
    """Matches the answer to the POST of the form action `name` of the page `route`, as `POST /?/add`."""

    def wanted(response: Any) -> bool:
        req = asked(response)
        parts = urlsplit(req.url)
        named = any(key == f"/{name}" for key, _ in parse_qsl(parts.query, keep_blank_values=True))
        return req.method == "POST" and on_route(route, parts.path) and named

    setattr(wanted, "text", f"POST {route}?/{name}")
    return wanted


def refusal(method: str, path: str) -> Wanted:
    """Matches a 4xx or 5xx answer to such a request."""
    wanted = request(method, path)
    return lambda response: wanted(asked(response)) and getattr(response, "status", 0) >= 400
