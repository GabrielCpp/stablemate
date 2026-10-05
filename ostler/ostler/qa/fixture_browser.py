"""A fixture step a browser performs: the screen it opens, then the acts it carries out there.

A sign-in a person makes through the app's own pages is arranged this way, so the session the
scenario starts in is the one a user would have. The harness performs the actions this module
resolves, on a page of the scenario's own browser, and keeps the session it leaves.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ostler import acts as acts_mod
from ostler import checks as checks_mod
from ostler import locators as loc_mod
from ostler import selector_forms
from ostler.model import Graph, UINode
from ostler.qa.runbook import bullet_text

BROWSER_KEYS = ("open", "arrange")

_ROLE_FORM = re.compile(r'role=([a-z]+)\[name="(.+)"\]')
_TEXT_FORMS = ("text", "label")
_ROUTE_PARAM = re.compile(r"(^|/)[:\[{*]|[\]}]")
_ACT_VALUE = {"fill": "value", "press": "key", "select": "option"}


@dataclass(frozen=True)
class BrowserStep:
    """What one fixture step asks a browser to do, or why the book cannot say it."""

    actions: list[dict[str, Any]] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def _values(meta: dict[str, Any], key: str) -> list[str]:
    raw = meta.get(key)
    if raw is None:
        return []
    items = raw if isinstance(raw, list) else [raw]
    return [str(item).strip() for item in items if str(item).strip()]


def is_browser_step(step: UINode) -> bool:
    """Whether *step* states a browser performance: an `open:` or an `arrange:` bullet."""
    return any(_values(step.meta, key) for key in BROWSER_KEYS)


def off_book_locator(value: str) -> dict[str, str] | None:
    """The locator *value* states for a page the book does not own: a role and name, a label, or a text."""
    text = value.strip()
    role = _ROLE_FORM.fullmatch(text)
    if role is not None:
        return {"role": role.group(1), "name": role.group(2)} if role.group(1) in loc_mod.ARIA_ROLES else None
    for form in _TEXT_FORMS:
        rest = text.removeprefix(f"{form}=")
        if rest != text and rest.strip():
            return {form: rest.strip()}
    return None


def _component_locator(node: UINode) -> dict[str, str] | None:
    role = bullet_text(next(iter(_values(node.meta, "role")), ""))
    name = bullet_text(next(iter(_values(node.meta, "name")), ""))
    if role and name:
        return {"role": role, "name": name.strip('"')}
    selector = bullet_text(next(iter(_values(node.meta, "selector")), ""))
    if not selector or selector_forms.parse_scheme_selector(selector) is not None:
        return None
    return {"css": selector}


def _locate(graph: Graph, step: UINode, value: str) -> dict[str, str] | str:
    node = loc_mod.located_node(graph, value, step.path)
    if node is not None:
        found = _component_locator(node)
        return found if found is not None else (
            f"`{value}` names {node.id}, which declares neither a `role:` and `name:` nor a CSS "
            f"`selector:` to find it by")
    if loc_mod.locator_target(graph, value, step.path):
        return f"`{value}` names no component or interaction this book declares"
    found = off_book_locator(value)
    if found is not None:
        return found
    return (f"`{value}` is neither a book anchor nor a locator for a page the book does not own: "
            f'`role=<role>[name="<name>"]`, `label=<label>` or `text=<text>`')


def _open(graph: Graph, step: UINode, value: str) -> dict[str, Any] | str:
    href = re.search(r"\]\(([^)]+)\)", value)
    target = graph.find_ui_node(graph.resolve_doc_ref(href.group(1), origin=step.path)) if href else None
    if target is None or target.type != "screen":
        return f"`open: {value}` links no `screen` — link the screen the browser starts on"
    route = bullet_text(next(iter(_values(target.meta, "route")), ""))
    if not route.startswith("/") or _ROUTE_PARAM.search(route):
        return (f"`open:` links {target.id}, whose route `{route}` is not one concrete path — "
                f"open a screen a person reaches by its address alone")
    return {"open": route, "screen": target.id}


def _act(graph: Graph, step: UINode, value: str) -> dict[str, Any] | str:
    parsed = acts_mod.parse_act(value)
    if isinstance(parsed, checks_mod.Refusal):
        return f"`arrange: {value}` {parsed.message}"
    if acts_mod.WEB not in acts_mod.ACT_BY_NAME[parsed.name].drivers:
        return f"`arrange: {value}` is not an act a browser performs"
    located = _locate(graph, step, str(parsed.args["locator"]))
    if isinstance(located, str):
        return located
    action: dict[str, Any] = {"act": parsed.name, "locator": located}
    value_param = _ACT_VALUE.get(parsed.name)
    if value_param is not None:
        action["value"] = str(parsed.args[value_param])
    return action


def browser_step(graph: Graph, step: UINode) -> BrowserStep:
    """*step*'s `open:` then its `arrange:` acts, in book order, each resolved to what the browser does."""
    resolved = BrowserStep()
    opens = _values(step.meta, "open")
    if len(opens) > 1:
        resolved.problems.append("states more than one `open:` — give each screen its own step")
    if _values(step.meta, "run"):
        resolved.problems.append("states both `run:` and a browser act — a step has one performer")
    entries = [_open(graph, step, value) for value in opens[:1]]
    entries += [_act(graph, step, value) for value in _values(step.meta, "arrange")]
    for entry in entries:
        if isinstance(entry, str):
            resolved.problems.append(entry)
        else:
            resolved.actions.append(entry)
    return resolved
