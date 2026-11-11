from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ostler.qa import context as qa_context

BOOK = "docs/services/api/"

OBLIGATIONS: list[dict[str, Any]] = [
    {"id": "held", "node": f"{BOOK}lists.md#share", "required": True},
    {"id": "optional", "node": f"{BOOK}lists.md#nice", "required": False},
    {"id": "other", "node": "docs/services/web/pages.md#home", "required": True},
    {
        "id": "already",
        "node": f"{BOOK}lists.md#held",
        "required": True,
        "deferred": {"kind": "no-check", "detail": "no runnable check"},
    },
]

DEFERRAL = {"prefix": BOOK, "kind": "book", "detail": "judged by the executable book of api"}


@pytest.fixture
def built(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    def fake(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "obligations": [dict(o) for o in OBLIGATIONS],
            "healthFindings": list(findings),
            "inputs": {},
        }

    monkeypatch.setattr(qa_context, "build_context", fake)
    monkeypatch.setattr(qa_context, "annotate_deferred_obligations", lambda packet: packet)

    def write(packet: dict[str, Any], spec_dir: Path) -> tuple[Path, Path]:
        target = spec_dir / "qa-okf-context.json"
        target.write_text(json.dumps(packet), encoding="utf-8")
        return target, spec_dir / "qa-okf-context.md"

    monkeypatch.setattr(qa_context, "write_context", write)
    return findings


def _build(tmp_path: Path) -> tuple[Any, dict[str, Any]]:
    spec = tmp_path / "spec"
    spec.mkdir(exist_ok=True)
    outcome = qa_context.cmd_context(tmp_path, spec, base="HEAD")
    packet = json.loads((spec / "qa-okf-context.json").read_text(encoding="utf-8"))
    return outcome, {o["id"]: o.get("deferred") for o in packet["obligations"]}


def test_the_build_defers_required_undeferred_obligations_under_a_prefix(
    tmp_path: Path, built: list[dict[str, Any]]
) -> None:
    (tmp_path / "spec").mkdir()
    (tmp_path / "spec" / "qa-deferrals.json").write_text(json.dumps([DEFERRAL]), encoding="utf-8")

    _, deferred = _build(tmp_path)

    assert deferred == {
        "held": {"kind": "book", "detail": "judged by the executable book of api"},
        "optional": None,
        "other": None,
        "already": {"kind": "no-check", "detail": "no runnable check"},
    }


def test_an_invalid_packet_still_carries_the_marks(
    tmp_path: Path, built: list[dict[str, Any]]
) -> None:
    built.append({"severity": "error", "message": "a page cites a deleted file"})
    (tmp_path / "spec").mkdir()
    (tmp_path / "spec" / "qa-deferrals.json").write_text(json.dumps([DEFERRAL]), encoding="utf-8")

    outcome, deferred = _build(tmp_path)

    assert outcome.ok is False
    assert deferred["held"] == {"kind": "book", "detail": "judged by the executable book of api"}


def test_no_file_and_an_empty_list_defer_nothing(
    tmp_path: Path, built: list[dict[str, Any]]
) -> None:
    _, absent = _build(tmp_path)
    (tmp_path / "spec" / "qa-deferrals.json").write_text("[]", encoding="utf-8")
    _, empty = _build(tmp_path)

    assert absent["held"] is None and empty["held"] is None
