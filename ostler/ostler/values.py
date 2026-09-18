"""The grammars declared on ``BulletKey.value_kind`` — one parser per kind, never a second one.

``BulletKey`` has sixteen flags saying what a value is *for* and, before ``value_kind``, nothing
saying what it may *say*. A key's required-ness is a statement about presence, and presence is
not a type, so a bullet like ``- method: fetch-data`` cleared every check in the book and reached
the compiler as a raw string. ``value_kind`` closes that gap the only way that does not reopen it
one level up: **a declared kind names the parser its consumer already uses, never a new grammar
invented for the declaration.** A kind that re-spells a grammar instead of calling its reader
recreates the exact defect this module exists to close — as many grammars for one key as it has
readers.

Each entry below delegates to an existing reader:

- ``"route"`` — :func:`ostler.routes.is_path_shaped`, the same line the plan compiler already
  draws between a ``screen.route``/``endpoint.path`` that could not possibly be a path and one
  that could, with its reason beside it as :data:`ostler.routes.NOT_PATH_SHAPED_REASON`. A
  parameterised route (``/policies/{id}``, ``/links/:id/edit``) is legal here: it names a
  family of pages, which ``screen.md`` hands to ``unidentifiable-screen`` downstream, not to
  this check.
- ``"door"`` — :func:`ostler.reach.is_route`, the exact predicate that decides whether a
  ``screen.entry`` value seeds reachability, with its reason kept beside it as
  :data:`ostler.reach.NOT_A_ROUTE_REASON`. Prose fails it precisely because the reachability
  walk already treats prose as unusable.
- ``"url"`` — an absolute URL: ``urlsplit`` with a ``http``/``https`` scheme and a non-empty
  netloc. No existing consumer parses ``server.entry-url``/``runbook.entry-url`` today beyond
  using it as a base to join a health path onto, so this is the one kind stated directly rather
  than delegated — the shape a *base URL* must have to be joinable at all.
- ``"http-method"`` — the same recognized-verb tuple :mod:`ostler.qa.compile` tests ``method:``
  against when it compiles a plan (``_HTTP_METHODS``), imported from there rather than copied.

Before any of those runs, every value passes through :func:`ostler.qa.runbook.bullet_text`, the
string-level half of :func:`ostler.qa.runbook.bullet_value` split out so this module calls the
same extraction rather than copying it. The book writes these values as markdown, so
`` - route: `/policies` `` is the ordinary spelling, and ``node.meta`` hands that back with
the backticks still on it — a reader that skips this step is not reading the value the way
its consumer does, it is reading the markdown *around* it.
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlsplit

from ostler.qa.compile import _HTTP_METHODS
from ostler.qa.runbook import bullet_text
from ostler.reach import NOT_A_ROUTE_REASON, is_route
from ostler.routes import NOT_PATH_SHAPED_REASON, is_path_shaped


def _route(value: str) -> str:
    """A path syntax, literal or parameterised — never a judgement on which of those it is.

    `why_unreadable` answers a *stricter* question for the walk-time reader it serves, which
    needs one literal URL to compare a screenshot against, so it also rejects a parameterised
    route. That is `unidentifiable-screen`'s question, asked once a scenario tries to compile,
    and this kind must not pre-empt it: `screen.md` is explicit that a param route is a legal
    thing for `route:`/`path:` to say. So this check asks only `is_path_shaped`, which leaves
    it exactly one way to fail and one reason to give.

    That reason names no bullet. This parser serves `screen.route` *and* `endpoint.path`, and
    `why_unreadable`'s wording is written for the first — an endpoint told its `route:` is not
    "a path a browser could show" is sent to a bullet it does not have, about a browser that
    never renders it.
    """
    if is_path_shaped(bullet_text(value)):
        return ""
    return NOT_PATH_SHAPED_REASON


def _door(value: str) -> str:
    if is_route(bullet_text(value)):
        return ""
    return NOT_A_ROUTE_REASON


def _url(value: str) -> str:
    parts = urlsplit(bullet_text(value))
    if parts.scheme in ("http", "https") and parts.netloc:
        return ""
    return "it is not an absolute `http(s)://` URL"


def _http_method(value: str) -> str:
    if bullet_text(value).upper() in _HTTP_METHODS:
        return ""
    return "it does not spell one of " + "/".join(_HTTP_METHODS)


#: kind name -> parser. Returns ``""`` when *value* is acceptable, a short human reason otherwise.
VALUE_KINDS: dict[str, Callable[[str], str]] = {
    "route": _route,
    "door": _door,
    "url": _url,
    "http-method": _http_method,
}
