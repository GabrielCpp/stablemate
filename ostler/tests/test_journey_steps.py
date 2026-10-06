"""Which links of a flow's `steps:` a journey performs, and which only place or explain a step."""

from __future__ import annotations

from ostler.qa.journey_steps import journey_steps
from ostler.qa.obligation_frame import BookNode, NodeEdge

_SHELL = "docs/features/web-app/gui/screens/shell.md"
_API = "docs/features/api-service/http/manifest.md"
_FORMAT = "docs/features/api-service/formats/manifest.md"


def _node(node_id: str, node_type: str, surface: str, edges: dict[str, tuple[str, str]] | None = None,
          steps: tuple[str, ...] = ()) -> BookNode:
    return BookNode(
        id=node_id, type=node_type, page_type="", surface=surface,
        bullets={"steps": steps} if steps else {},
        edges=tuple(NodeEdge(to=to, via=via, href=href) for href, (to, via) in (edges or {}).items()),
    )


def _book(*steps: str) -> tuple[BookNode, dict[str, BookNode]]:
    nodes = [
        _node(_SHELL, "screen", "web-app"),
        _node(f"{_SHELL}#fetch-manifest", "invocation", "web-app",
              edges={"../api.md": (_API, "on")}),
        _node(f"{_SHELL}#open-menu", "interaction", "web-app"),
        _node(f"{_SHELL}#fetch-error", "component", "web-app"),
        _node(_API, "endpoint", "api-service"),
        _node(f"{_FORMAT}#field-pages", "field", "api-service"),
    ]
    links = {
        "shell.md": (_SHELL, "steps"),
        "shell.md#fetch-manifest": (f"{_SHELL}#fetch-manifest", "steps"),
        "shell.md#open-menu": (f"{_SHELL}#open-menu", "steps"),
        "shell.md#fetch-error": (f"{_SHELL}#fetch-error", "steps"),
        "api.md": (_API, "steps"),
        "format.md#field-pages": (f"{_FORMAT}#field-pages", "steps"),
    }
    flow = _node("docs/features/web-app/flows/f.md", "flow", "web-app", edges=links, steps=steps)
    return flow, {node.id: node for node in nodes}


def _walk(*steps: str) -> list[tuple[str, str]]:
    flow, book = _book(*steps)
    return [(step.ref.rsplit("/", 1)[-1], step.node_type) for step in journey_steps(flow, book)]


def test_a_place_beside_an_action_is_where_the_action_happens() -> None:
    walk = _walk("[open-menu](shell.md#open-menu) on [shell](shell.md), showing "
                 "[fetch-error](shell.md#fetch-error) and [pages](format.md#field-pages)")
    assert walk == [("shell.md#open-menu", "interaction")]


def test_an_endpoint_the_journeys_invocation_calls_is_its_request_not_a_second_service() -> None:
    walk = _walk("[fetch-manifest](shell.md#fetch-manifest) sends one GET to [manifest](api.md)",
                 "[open-menu](shell.md#open-menu)")
    assert walk == [("shell.md#fetch-manifest", "invocation"), ("shell.md#open-menu", "interaction")]


def test_an_endpoint_no_invocation_calls_is_still_a_step() -> None:
    walk = _walk("[open-menu](shell.md#open-menu)", "an operator calls [manifest](api.md)")
    assert walk == [("shell.md#open-menu", "interaction"), ("manifest.md", "endpoint")]


def test_a_bullet_naming_only_places_is_what_the_reader_sees_not_a_step() -> None:
    walk = _walk("[open-menu](shell.md#open-menu)", "[fetch-error](shell.md#fetch-error) mounts on [shell](shell.md)")
    assert walk == [("shell.md#open-menu", "interaction")]


def test_an_unresolved_link_stays_so_the_walk_is_refused_rather_than_shortened() -> None:
    walk = _walk("[open-menu](shell.md#open-menu) then [gone](shell.md#gone)")
    assert walk == [("shell.md#open-menu", "interaction"), ("", "")]
