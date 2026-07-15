from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "checkpoint.py"
SPEC = importlib.util.spec_from_file_location("okf_checkpoint", SCRIPT)
assert SPEC and SPEC.loader
checkpoint = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checkpoint)


def test_doctor_filters_unrelated_repository_findings(tmp_path, monkeypatch):
    service = tmp_path / "docs/features/api"
    service.mkdir(parents=True)
    report = {
        "findings": [
            {"severity": "error", "path": "docs/specs/old/plan.md", "message": "old"},
            {"severity": "error", "path": "docs/features/api/http/server.md", "message": "api"},
            {"severity": "warn", "path": "docs/features/api/http/server.md", "message": "warning"},
            {"severity": "error", "path": "docs/features/web/gui/home.md", "message": "web"},
        ]
    }

    class Result:
        stdout = json.dumps(report)

    monkeypatch.setattr(checkpoint.subprocess, "run", lambda *args, **kwargs: Result())

    findings, rendered = checkpoint._doctor_for_features(str(tmp_path), str(service))

    assert [finding["message"] for finding in findings] == ["api"]
    assert "old" not in rendered
