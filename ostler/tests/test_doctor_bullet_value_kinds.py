"""`doctor` holds a bullet whose key declares a `value_kind` to the parser its consumer runs.

`BulletKey.required` checks presence only — a role, not a grammar. `value_kind` is the flag
that says what the value may *say*, checked by calling the exact parser a consumer (the route
reader, the reachability walk, the HTTP-verb table) already runs over it, never a second one
invented for the declaration. See `ostler.values` and `_check_bullet_value_kinds` (doctor.py).
"""

from __future__ import annotations

from pathlib import Path

from ostler import doctor
from ostler.model import load

from conftest import write

SCREEN_PATH = "docs/features/acme/screens/widgets.md"
ENDPOINT_PATH = "docs/features/acme/server.md"


def _screen_book(route: str = "/widgets", entry: str = "") -> str:
    lines = ["---", "type: screen", "slug: widgets", "title: Widgets", "---", "# Widgets", "",
              f"- route: {route}", "- requires: none", "- params: none"]
    if entry:
        lines.append(f"- entry: {entry}")
    lines.append("")
    return "\n".join(lines)


def _endpoint_book(method: str = "GET", path: str = "/api/accounts") -> str:
    return f"""---
type: server
title: Acme accounts
---
# Acme accounts

## Endpoints

### list-accounts
- method: {method}
- path: {path}
- authorization: an adjuster reads every account on file.
"""


def _findings(repo: Path, code: str) -> list[doctor.Finding]:
    return [f for f in doctor.run(load(repo)).findings if f.code == code]


def test_a_nonparsing_http_method_is_reported(repo: Path) -> None:
    write(repo / ENDPOINT_PATH, _endpoint_book(method="fetch-data"))
    found = _findings(repo, "unparsable-bullet-value")
    assert [(f.severity, "#method:" in f.ref) for f in found] == [("error", True)]
    assert "method: fetch-data" in found[0].message
    assert "http-method" in found[0].message


def test_a_valid_http_method_is_clean(repo: Path) -> None:
    write(repo / ENDPOINT_PATH, _endpoint_book(method="POST"))
    assert _findings(repo, "unparsable-bullet-value") == []


def test_a_prose_entry_is_reported(repo: Path) -> None:
    write(repo / SCREEN_PATH, _screen_book(entry="no; it is reached from the dashboard"))
    found = _findings(repo, "unparsable-bullet-value")
    entry_findings = [f for f in found if "#entry:" in f.ref]
    assert len(entry_findings) == 1
    assert "entry: no; it is reached from the dashboard" in entry_findings[0].message
    assert "door" in entry_findings[0].message


def test_a_route_valued_entry_is_clean(repo: Path) -> None:
    write(repo / SCREEN_PATH, _screen_book(entry="/login"))
    found = [f for f in _findings(repo, "unparsable-bullet-value") if "#entry:" in f.ref]
    assert found == []


def test_an_absolute_url_entry_is_clean(repo: Path) -> None:
    write(repo / SCREEN_PATH, _screen_book(entry="https://accounts.example.com/callback"))
    found = [f for f in _findings(repo, "unparsable-bullet-value") if "#entry:" in f.ref]
    assert found == []


def test_a_parameterized_route_does_not_raise(repo: Path) -> None:
    write(repo / SCREEN_PATH, _screen_book(route="/widgets/{id}"))
    found = [f for f in _findings(repo, "unparsable-bullet-value") if "#route:" in f.ref]
    assert found == []


def test_a_backtick_wrapped_route_is_clean(repo: Path) -> None:
    """The corpus writes `route:` as a markdown code span (`` `/widgets` ``), same as `role:`.

    `node.meta` hands the value back with the backticks still on it; the value kind must
    unwrap it the same way `ostler.routes.screen_routes` and `bullet_value` already do, not
    fall through to `why_unreadable` on a string that merely *starts* with a backtick.
    """
    write(repo / SCREEN_PATH, _screen_book(route="`/widgets`"))
    found = [f for f in _findings(repo, "unparsable-bullet-value") if "#route:" in f.ref]
    assert found == []


def test_an_absent_entry_bullet_does_not_raise(repo: Path) -> None:
    write(repo / SCREEN_PATH, _screen_book())
    found = [f for f in _findings(repo, "unparsable-bullet-value") if "#entry:" in f.ref]
    assert found == []


def test_a_valid_endpoint_path_is_clean(repo: Path) -> None:
    write(repo / ENDPOINT_PATH, _endpoint_book(path="/api/accounts/{id}"))
    found = [f for f in _findings(repo, "unparsable-bullet-value") if "#path:" in f.ref]
    assert found == []


def test_a_valid_server_entry_url_is_clean(repo: Path) -> None:
    write(repo / "docs/features/app/ops/qa-stack.md", (
        "---\ntype: runbook\ntitle: QA stack\n---\n\n# QA stack\n\n"
        "- driver: web\n- entry-url: http://localhost:18099\n\n"
        "## Steps\n\n### serve\n\n- kind: service\n- run: ./serve.sh\n"
    ))
    found = [f for f in _findings(repo, "unparsable-bullet-value")
             if "#entry-url:" in f.ref]
    assert found == []


def test_a_malformed_server_entry_url_is_reported(repo: Path) -> None:
    write(repo / "docs/features/app/ops/qa-stack.md", (
        "---\ntype: runbook\ntitle: QA stack\n---\n\n# QA stack\n\n"
        "- driver: web\n- entry-url: localhost:18099\n\n"
        "## Steps\n\n### serve\n\n- kind: service\n- run: ./serve.sh\n"
    ))
    found = [f for f in _findings(repo, "unparsable-bullet-value")
             if "#entry-url:" in f.ref]
    assert len(found) == 1
    assert "url" in found[0].message
