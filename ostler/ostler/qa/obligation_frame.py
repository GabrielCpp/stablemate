"""The frame every obligation of a book node shares: its surface, journey, locators and repeat contract."""

from __future__ import annotations

from typing import Any

from ostler import locators as locators_mod
from ostler import markdown, registry
from ostler.qa.packet_rows import JourneyStep, ObligationFrame, RepeatContract, RepeatTemplate, Segment

_LOCATOR_KEYS = tuple(sorted(registry.LOCATOR_KEYS))
_LOCATOR_KEY_RENAME = {"exclusive-with": "exclusiveWith"}


def bullet_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)] if value else []


def declared_locators(node: dict[str, Any]) -> dict[str, list[str]]:
    declared = registry.declared_keys(node.get("type", ""))
    bullets = node.get("bullets", {})
    return {
        _LOCATOR_KEY_RENAME.get(key, key): bullet_values(bullets.get(key))
        for key in _LOCATOR_KEYS
        if key in declared and bullet_values(bullets.get(key))
    }


def extends_target(
    node: dict[str, Any], nodes_by_id: dict[str, dict[str, Any]]
) -> tuple[dict[str, Any] | None, bool]:
    """The base node an `extends:` arm inherits its control identity from (D51)."""
    to_ids = [
        edge.get("to")
        for edge in node.get("edges") or []
        if edge.get("via") == "extends" and edge.get("to")
    ]
    if not to_ids:
        return None, False
    target = nodes_by_id.get(str(to_ids[0]))
    if target is None or target.get("type") != node.get("type"):
        return None, True
    return target, False


def page_type(node: dict[str, Any]) -> str:
    """The type of the page *node* sits on: its own type for a page, its page's for a section."""
    type_path = node.get("type_path") or [node.get("type", "")]
    return str(type_path[0])


def _endpoint_address(
    node: dict[str, Any], nodes_by_id: dict[str, dict[str, Any]]
) -> dict[str, list[str]]:
    """The address of the endpoint an invocation's `on:` names, which the invocation calls."""
    for edge in node.get("edges") or []:
        target = nodes_by_id.get(str(edge.get("to"))) if edge.get("via") == "on" else None
        if target is not None and target.get("type") == "endpoint":
            located = declared_locators(target)
            return {key: located[key] for key in registry.address_keys("endpoint") if key in located}
    return {}


def linked_surface(
    node: dict[str, Any], value: Any, nodes_by_id: dict[str, dict[str, Any]]
) -> str:
    """The surface of the node *value*'s own links point at — "" when they point at none."""
    hrefs = {
        href
        for item in bullet_values(value)
        for _text, href in markdown.extract_refs(item).links
    }
    if not hrefs:
        return ""
    for edge in node.get("edges") or []:
        target_id = edge.get("to")
        if not target_id or edge.get("href") not in hrefs:
            continue
        target = nodes_by_id.get(str(target_id))
        if target and target.get("surface"):
            return str(target["surface"])
    return ""


def _journey_steps(
    node: dict[str, Any], nodes_by_id: dict[str, dict[str, Any]]
) -> tuple[JourneyStep, ...]:
    """The nodes a flow's `steps:` names, in the order the book wrote them."""
    resolved = {
        str(edge["href"]): str(edge["to"])
        for edge in node.get("edges") or []
        if edge.get("to") and edge.get("href")
    }
    walk: list[JourneyStep] = []
    for item in bullet_values(node.get("bullets", {}).get("steps")):
        for _text, href in markdown.extract_refs(item).links:
            target_id = resolved.get(href, "")
            target = nodes_by_id.get(target_id, {}) if target_id else {}
            walk.append(
                JourneyStep(
                    ref=target_id,
                    href=href,
                    node_type=str(target.get("type") or ""),
                    surface=str(target.get("surface") or ""),
                )
            )
    return tuple(walk)


def _repeat(node: dict[str, Any], scope: tuple[str, ...]) -> RepeatContract | None:
    """The compiled repeat contract for a node in a `one-per:` scope, or None."""
    own = locators_mod.repeat_of(node)
    scope = scope or ((own,) if own else ())
    if not scope:
        return None
    located = locators_mod.locator_for(node, scope=scope)
    template, binds = None, ()
    if located["strategy"] == "template":
        template = RepeatTemplate(
            template=str(located["template"]),
            iterates=str(located["iterates"]),
            segments=tuple(Segment.parse(segment) for segment in located["segments"]),
        )
        binds = tuple(str(bind) for bind in located["binds"])
    return RepeatContract(
        one_per=scope[-1],
        binds=binds,
        template=template,
        unique_by=locators_mod.unique_by_of(node),
        variants=locators_mod.variants_of(node),
    )


def obligation_frame(
    node: dict[str, Any], scope: tuple[str, ...], nodes_by_id: dict[str, dict[str, Any]] | None
) -> ObligationFrame:
    """The frame every obligation of *node* shares."""
    surface, steps = "", ()
    if nodes_by_id is not None and node.get("type") == "flow":
        surface = linked_surface(node, node.get("bullets", {}).get("end"), nodes_by_id)
        steps = _journey_steps(node, nodes_by_id)
    locators = declared_locators(node)
    extends_unresolved = False
    if nodes_by_id is not None and node.get("type") in ("interaction", "invocation"):
        base, extends_malformed = extends_target(node, nodes_by_id)
        if base is not None:
            locators = {**declared_locators(base), **locators}
        else:
            extends_unresolved = extends_malformed
    if nodes_by_id is not None and node.get("type") == "invocation":
        locators = {**_endpoint_address(node, nodes_by_id), **locators}
    return ObligationFrame(
        surface=surface,
        steps=steps,
        on_cli_page=page_type(node) == "cli",
        locators=locators,
        extends_unresolved=extends_unresolved,
        repeat=_repeat(node, scope),
    )

