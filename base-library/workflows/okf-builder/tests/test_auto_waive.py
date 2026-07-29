"""auto-waive: accept code-fix-only a11y defects with a waiver + IOU; never paper over the rest.

The node runs only when the fixup loop has already stalled, so its whole job is the partition:
a defect the source alone can fix (ambiguous-locator, unnamed-interactive) is accepted — a
downgrading waiver plus a backlog IOU that names the fix and the way back — while anything a doc
edit could still fix must NOT be waived, and instead routes the run to the honest doctor_stuck exit.
"""
from __future__ import annotations

import importlib.util
import json
import logging
import types
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "auto-waive.py"
SPEC = importlib.util.spec_from_file_location("okf_auto_waive", SCRIPT)
assert SPEC and SPEC.loader
aw = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(aw)


class FakeOstler:
    def __init__(self, report: dict, backlog: list) -> None:
        self._report = report
        self.graph = object()          # opaque; the fake backlog module ignores it
        self.waivers: list[tuple] = []
        self._backlog = backlog
        self._next = 0

    def doctor(self) -> dict:
        return self._report

    def allocate_id(self) -> str:
        self._next += 1
        return f"PRED-{self._next}"     # ostler-minted, repo-prefixed numbering

    def add_doctor_waiver(self, code, ref, reason, backlog=""):
        self.waivers.append((code, ref, backlog))


def _err(code: str, ref: str) -> dict:
    return {"severity": "error", "code": code, "ref": ref,
            "path": ref.split("#", 1)[0], "message": f"{code} on {ref}",
            "suggestion": "give each control a distinct accessible name"}


def _run(tmp_path, report, monkeypatch, capsys):
    backlog: list = []
    fake = FakeOstler(report, backlog)
    fake.backlog = backlog                    # expose for assertions
    # The script imports ostler at module scope (a workflow that cannot import it never
    # reaches node one — `requires: dist: ostler`), so the seam is the loaded script's own
    # attributes. Patching sys.modules here would be too late: the names are already bound.
    backlog_mod = types.ModuleType("ostler.backlog")
    backlog_mod.add = lambda graph, item_id, text, section="": backlog.append((item_id, text, section))
    monkeypatch.setattr(aw, "Ostler", lambda root: fake)
    monkeypatch.setattr(aw, "backlog_mod", backlog_mod)
    features = tmp_path / "docs/features/web"
    monkeypatch.setattr("sys.argv", ["auto-waive.py", str(tmp_path), str(features), "web"])
    with pytest.raises(SystemExit):
        aw.main(logging.getLogger("t"))
    return json.loads(capsys.readouterr().out), fake


def test_waivable_defects_are_waived_and_get_a_backlog_iou(tmp_path, monkeypatch, capsys):
    report = {"findings": [
        _err("ambiguous-locator", "docs/features/web/gui/components/navbar.md#s/save"),
        _err("unnamed-interactive", "docs/features/web/gui/components/navbar.md#s/icon"),
    ]}
    out, fake = _run(tmp_path, report, monkeypatch, capsys)

    assert out["has_unwaivable"] == "no"
    assert out["waived_count"] == 2
    assert len(fake.waivers) == 2 and len(fake.backlog) == 2
    # every IOU carries an ostler-minted numbered id (not a descriptive slug), and the waiver
    # references that same id
    assert [item_id for item_id, _, _ in fake.backlog] == ["PRED-1", "PRED-2"]
    for (code, ref, backlog), (item_id, text, section) in zip(fake.waivers, fake.backlog):
        assert backlog == item_id and item_id.startswith("PRED-")
        assert "doctor-waivers.json" in text          # how to un-waive
        assert "recheck_only" in text                 # how to re-run and confirm
        assert "web" in text


def test_a_non_waivable_stalled_finding_routes_to_doctor_stuck(tmp_path, monkeypatch, capsys):
    report = {"findings": [
        _err("ambiguous-locator", "docs/features/web/gui/components/navbar.md#s/save"),
        _err("missing-required-bullet", "docs/features/web/gui/screens/home.md#s/x"),  # doc-fixable
    ]}
    out, fake = _run(tmp_path, report, monkeypatch, capsys)

    assert out["has_unwaivable"] == "yes"
    assert out["waived_count"] == 0        # nothing waived — the run fails honestly instead
    assert fake.waivers == [] and fake.backlog == []


def test_findings_outside_the_service_book_are_ignored(tmp_path, monkeypatch, capsys):
    report = {"findings": [_err("ambiguous-locator", "docs/specs/legacy/plan.md#s/x")]}
    out, fake = _run(tmp_path, report, monkeypatch, capsys)

    assert out["has_unwaivable"] == "no"
    assert out["waived_count"] == 0        # out of scope → nothing standing to waive
    assert "nothing to waive" in out["note"]


def test_already_waived_warn_findings_are_not_re_waived(tmp_path, monkeypatch, capsys):
    # A prior waiver downgraded it to warn; only error-severity findings are in scope.
    report = {"findings": [
        {"severity": "warn", "code": "ambiguous-locator", "waived": True,
         "ref": "docs/features/web/gui/components/navbar.md#s/save",
         "path": "docs/features/web/gui/components/navbar.md", "message": "already waived"},
    ]}
    out, fake = _run(tmp_path, report, monkeypatch, capsys)

    assert out["waived_count"] == 0 and fake.waivers == []
