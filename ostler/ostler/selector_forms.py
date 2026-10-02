"""What a component's `selector:` bullet says about the address each driver can query."""

from __future__ import annotations

import re

from collections.abc import Callable


ROLE_SELECTOR = re.compile(r"""^([a-zA-Z][\w-]*)?\[role=["']([\w-]+)["']\]$""")

_STRING_SELECTOR = re.compile(r"^(?:#[\w-]+|[a-zA-Z][\w-]*(?:\.[\w-]+)*)$")

_SCHEME_SELECTOR = re.compile(r"^([A-Za-z][\w-]*)=(.+)$")

SELECTOR_SCHEMES: frozenset[str] = frozenset({"testID"})


def parse_scheme_selector(selector: str) -> tuple[str, str] | None:
    """`(scheme, value)` for a self-identifying selector naming a known scheme, else `None`."""
    matched = _SCHEME_SELECTOR.match(selector)
    if matched is None:
        return None
    scheme, value = matched.group(1), matched.group(2)
    return (scheme, value) if scheme in SELECTOR_SCHEMES else None


def is_addressable(selector: str) -> bool:
    """Whether *selector* is a form `ostler vet`'s screen census can ever resolve, **or** a self-identifying address the census was never going to resolve for an honest reason."""
    if parse_scheme_selector(selector) is not None:
        return True
    return bool(ROLE_SELECTOR.match(selector) or _STRING_SELECTOR.match(selector))


def is_web_representable(selector: str) -> bool:
    """Whether *selector* could be handed to a web DOM driver — false for a `scheme=value` address written against a component whose surface a browser drives."""
    return parse_scheme_selector(selector) is None


NOT_WEB_REPRESENTABLE_REASON = (
    "it is a `scheme=value` address (a non-web selector, e.g. `testID=...`), and this "
    "component's surface is driven by a browser, which queries the DOM, not a scheme"
)

_DOM_LEADING_ID_OR_CLASS = re.compile(r"^[#.][A-Za-z_-]")
_DOM_ATTRIBUTE_PREDICATE = re.compile(r"\[[^\]]*\]")
_DOM_COMBINATOR = re.compile(r"[>~]")
_DOM_COMPOUND_TAG = re.compile(r"^[A-Za-z][\w-]*[.#][\w-]+")


def is_mobile_representable(selector: str) -> bool:
    """Whether *selector* could be a Maestro address — false only for a string that unmistakably names DOM syntax instead."""
    text = selector.strip()
    return not (
        _DOM_LEADING_ID_OR_CLASS.match(text)
        or _DOM_ATTRIBUTE_PREDICATE.search(text)
        or _DOM_COMBINATOR.search(text)
        or _DOM_COMPOUND_TAG.match(text)
    )


NOT_MOBILE_REPRESENTABLE_REASON = (
    "it is DOM syntax (an id, a class, an attribute predicate, a combinator, or a "
    "tag.class/tag#id compound), and this component's surface is driven by Maestro, which "
    "resolves a control by a `scheme=value` address (e.g. `testID=...`) or by its visible "
    "text, never by CSS"
)


def is_never_selected(selector: str) -> bool:
    """Always false — the predicate for a driver whose surface renders nothing to query."""
    del selector
    return False


NEVER_SELECTED_REASON = (
    "this driver renders nothing to query — it owns no `screen`/`component` node at all"
)


SELECTOR_GRAMMAR: dict[str, tuple[Callable[[str], bool], str]] = {
    "web": (is_web_representable, NOT_WEB_REPRESENTABLE_REASON),
    "mobile": (is_mobile_representable, NOT_MOBILE_REPRESENTABLE_REASON),
    "http": (is_web_representable, NOT_WEB_REPRESENTABLE_REASON),
    "cli": (is_never_selected, NEVER_SELECTED_REASON),
    "iac": (is_never_selected, NEVER_SELECTED_REASON),
    "artifact": (is_never_selected, NEVER_SELECTED_REASON),
    "none": (is_never_selected, NEVER_SELECTED_REASON),
}

_DEFAULT_SELECTOR_GRAMMAR: tuple[Callable[[str], bool], str] = (lambda _selector: True, "")


def selector_grammar(driver: str | None) -> tuple[Callable[[str], bool], str]:
    """The `(predicate, reason)` pair *driver* is held to for a `selector:` bullet."""
    predicate, reason = SELECTOR_GRAMMAR.get(driver or "", _DEFAULT_SELECTOR_GRAMMAR)
    return predicate, reason
