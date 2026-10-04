"""What the page, endpoint and mobile builders of `compile-plan` share past the plan source itself."""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from types import ModuleType

from ostler.markdown import extract_refs
from ostler.qa.harness_host import load_harness_module
from ostler.qa.obligation import CallRow
from ostler.qa.obligation import Obligation
from ostler.qa.plan_source import Gap
from ostler.qa.plan_source import arrangement_of
from ostler.qa.plan_source import check_observes
from ostler.qa.plan_source import python_literal
from ostler.routes import arrival_regex
from ostler.routes import is_comparable
from ostler.routes import is_screen_name_shaped
from ostler.routes import why_unreadable


@dataclass(frozen=True)
class DriverSpec:
    """A driver's declared observation channels — the other half of the observability relation."""
    name: str
    observes: frozenset[str]


def _declared_observations(harness: ModuleType) -> dict[str, frozenset[str]]:
    """Each driver the harness declares, by name, with the channels it observes, refusing a row of any other shape."""
    declared: dict[str, frozenset[str]] = {}
    for driver in harness.DRIVERS:
        name, observes = getattr(driver, "name", None), getattr(driver, "observes", None)
        if not isinstance(name, str) or not isinstance(observes, frozenset):
            raise TypeError(f"the harness declares a driver row {driver!r} with no string name and frozenset observes")
        declared[name] = frozenset(str(channel) for channel in observes)
    return declared


_OBSERVES = _declared_observations(load_harness_module("ostler_qa"))

PYTHON = DriverSpec("python", _OBSERVES["python"])

PLAYWRIGHT = DriverSpec("playwright", _OBSERVES["playwright"])

MAESTRO = DriverSpec("maestro", _OBSERVES["maestro"])


def unobservable_gap(oid: str, name: str | None, driver: DriverSpec) -> Gap:
    """*driver* cannot serve *name* — a real gap, not a silently dropped row."""
    observes = check_observes(name)
    what = f"a {observes}" if observes else "an unknown check"
    if observes is not None and observes in driver.observes:
        return Gap(oid, "uncompilable-claim",
                    f"`{name}` observes {what}, which the {driver.name} driver can see, but "
                    f"this compiler has no page-scenario arrangement for it yet")
    return Gap(oid, "uncompilable-claim",
               f"`{name}` observes {what}, not observable from the {driver.name} driver")


_CODE_SPAN = re.compile(r"^\s*`?\s*(.*?)\s*`?\s*$")

_NONE_SENTINEL = "none"


def bullet_value(raw: str | None) -> str | None:
    """*raw* as one line, stripped of a wrapping code span, with `none` read as absent."""
    if raw is None:
        return None
    match = _CODE_SPAN.match(" ".join(raw.split()))
    assert match is not None, "_CODE_SPAN matches any single line (its inner group is `.*?`)"
    value = match.group(1).strip()
    if not value or value.lower() == _NONE_SENTINEL:
        return None
    return value


def trailing_comment(text: str) -> str:
    """*text*, flattened onto one line, safe to follow real code on the same line."""
    return " ".join(text.split())


def on_href(on_value: str) -> str | None:
    """The link target an `on:` bullet names, when it names one."""
    return next(iter(extract_refs(on_value).links), (None, None))[1]


def on_node(source: str, on_value: str) -> str:
    """The node an `on:` bullet on page *source* links, on that page or on the page its link names; `""` with no link."""
    href = on_href(on_value)
    if not href:
        return ""
    page, _, anchor = href.partition("#")
    target = posixpath.normpath(posixpath.join(posixpath.dirname(source), page)) if page else source
    return f"{target}#{anchor}"


def on_label(on_value: str) -> str:
    """How a gap message names the node an `on:` bullet points at."""
    return (on_href(on_value) or on_value or "").lstrip("#") or on_value


def check_document(row: CallRow, obligation: Obligation) -> str:
    """The screen document a check observes — the one its `locator=` names, or its own."""
    for param in sorted(row.locates):
        node_id = row.locates[param].node
        if node_id:
            return node_id.split("#", 1)[0]
    return obligation.source


def why_unmatchable_screen_name(route: str) -> str:
    """Why *route* is not a screen name a Maestro flow's own report could be compared against."""
    text = route.strip()
    if not text:
        return "the book states no single `route:` for it"
    return f"its `route:` (`{text}`) is not a navigator screen name a Maestro run could match"


def vettable(
    documents: list[str],
    screen_routes: dict[str, str],
    ids: list[str],
    gaps: list[Gap],
    *,
    mobile: bool = False,
) -> list[str]:
    """*documents* a vet can establish as its subject, with a gap for each one it cannot."""
    keep: list[str] = []
    for document in documents:
        route = screen_routes.get(document, "")
        if is_screen_name_shaped(route.strip()) if mobile else is_comparable(route):
            keep.append(document)
            continue
        why = why_unmatchable_screen_name(route) if mobile else why_unreadable(route)
        gaps.extend(Gap(oid, "unidentifiable-screen",
                        f"this scenario ends on {document}, and {why} — so nothing can say the "
                        "page it photographed is that screen, and its placement verdicts are "
                        "withheld rather than reported about an unestablished subject")
                    for oid in ids)
    return keep


def unarranged_state_gap(obligation: Obligation) -> Gap:
    """The `unarranged-state` gap for one check-less `states:` obligation."""
    state_text = " ".join(obligation.requirement.split())
    missing = []
    if not obligation.checks:
        missing.append("no check declared — indent a `verify:` under this state's own bullet")
    if arrangement_of([obligation]).unstated:
        missing.append("no fixture arranged — indent a `fixture:` under this state's own bullet, "
                       "or `fixture: none, because ...` when the state holds as the screen opens")
    return Gap(obligation.id, "unarranged-state",
               f"carries `states:` ({state_text!r}); " + " and ".join(missing)
               + ". A state only a person's act reaches is the `does:` of the interaction that performs the act: claim it there")


def unarranged_scenario_gap(obligation: Obligation) -> Gap:
    """The `unarranged-scenario` gap for a claim whose state nothing established."""
    return Gap(obligation.id, "unarranged-scenario",
               "this claim's scenario arranges nothing before it observes and does not say it "
               "needs nothing — add a `fixture:` naming the arrangement, or "
               "`fixture: none, because ...` saying why the claim holds in whatever world the "
               "scenario finds")


def vet_calls(documents: list[str], screen_routes: dict[str, str], ids: list[str], gaps: list[Gap]) -> list[str]:
    """One `qa.vet` line per browser screen in *documents* a vet can establish, each told the address to wait for."""
    return [
        f"    qa.vet({python_literal(document)}, arrives={python_literal(arrival_regex(screen_routes.get(document, '')))})"
        for document in vettable(documents, screen_routes, ids, gaps)
    ]
