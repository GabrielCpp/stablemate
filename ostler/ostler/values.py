"""The grammars declared on ``BulletKey.value_kind`` — one parser per kind, never a second one.

``BulletKey`` has sixteen flags saying what a value is *for* and, before ``value_kind``, nothing
saying what it may *say*. A key's required-ness is a statement about presence, and presence is
not a type, so a bullet like ``- method: fetch-data`` cleared every check in the book and reached
the compiler as a raw string. ``value_kind`` closes that gap the only way that does not reopen it
one level up: **a declared kind names the parser its consumer already uses, never a new grammar
invented for the declaration.** A kind that re-spells a grammar instead of calling its reader
recreates the exact defect this module exists to close — as many grammars for one key as it has
readers.

A ``route:``/``path:`` bullet is *not* one of the entries below, even though ``BulletKey``
still names its kind ``"route"``: which grammar such a bullet is held to depends on the
node's surface driver (a browser's path, a mobile navigator's screen name, or no route at
all — see :data:`ostler.routes.ROUTE_GRAMMAR`), and a single ``VALUE_KINDS`` entry cannot
speak for a driver it is not given. Rather than pick one driver's grammar here and special-
case the rest in the caller, ``doctor.py``'s ``_check_bullet_value_kinds`` asks
:func:`ostler.routes.route_grammar` for the resolved driver's ``(predicate, reason)`` pair
directly and composes it into this module's message shape itself, for every driver alike.
``ROUTE_GRAMMAR`` is the single statement of that grammar; this module does not restate it.

A ``selector:`` bullet on a ``component`` is the same story with a different table: whether a
given string is CSS, a self-identifying ``scheme=value`` address, or neither is
:func:`ostler.vet.placement.is_addressable`'s question, deliberately driver-blind — but
*which of the two representations* the surface's own driver can query is not, and depends on
the node's driver the same way a route's does. ``doctor.py`` asks
:func:`ostler.vet.placement.selector_grammar` for that pair the same way it asks
``route_grammar``, and reports a mismatch as ``conflicting-selector-driver`` rather than
``unparsable-bullet-value`` — the value parsed fine, against the wrong representation.
``SELECTOR_GRAMMAR`` is that grammar's single statement.

Each entry below delegates to an existing reader:

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
    "url": _url,
    "http-method": _http_method,
}
