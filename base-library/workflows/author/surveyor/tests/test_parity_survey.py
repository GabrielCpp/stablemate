from __future__ import annotations

import json

from tests.conftest import init_repo, run_script, write_record


def test_expand_parity_inventory_excludes_rewrite_entries(tmp_path):
    init_repo(tmp_path)
    baseline = tmp_path / "docs/legacy/screens/inventory.json"
    baseline.parent.mkdir(parents=True)
    baseline.write_text(json.dumps({"entries": [
        {"area": "auth", "slug": "sign-in", "title": "Sign in", "route": "/login"},
        {"area": "web", "slug": "new-only", "rewriteSurface": True},
    ]}))

    out = run_script(
        "expand-parity-inventory.py",
        "docs/legacy/screens/inventory.json",
        "docs/survey/legacy-vs-new/inventory.json",
        repo=tmp_path,
    )

    assert out["expand_ok"] == "yes"
    inventory = json.loads((tmp_path / "docs/survey/legacy-vs-new/inventory.json").read_text())
    assert [u["id"] for u in inventory["units"]] == ["legacy/auth/sign-in"]
    assert inventory["units"][0]["path"] == "docs/legacy/screens/auth/sign-in.md"


def test_emit_parity_backlog_is_one_per_missing_and_suppresses_owned(tmp_path):
    init_repo(tmp_path)
    survey = tmp_path / "docs/survey/legacy-vs-new"
    survey.mkdir(parents=True)
    inventory = {
        "version": 1,
        "baseline": "docs/legacy/screens/inventory.json",
        "units": [
            {"id": "legacy/auth/sign-in", "path": "legacy.md", "kind": "legacy-surface",
             "status": "assessed", "area": "auth", "slug": "sign-in"},
            {"id": "legacy/admin/home", "path": "admin.md", "kind": "legacy-surface",
             "status": "assessed", "area": "admin", "slug": "home"},
            {"id": "legacy/errors/404", "path": "404.md", "kind": "legacy-surface",
             "status": "clean", "area": "errors", "slug": "404"},
        ],
    }
    (survey / "inventory.json").write_text(json.dumps(inventory))
    finding = [{"description": "Build sign-in parity for legacy /login.",
                "remediation_pattern": "legacy-surface-parity", "effort": "small",
                "evidence": "legacy.md:1; no current graph node"}]
    write_record(tmp_path, "legacy/auth/sign-in", findings=finding,
                 findings_dir="docs/survey/legacy-vs-new/findings")
    write_record(tmp_path, "legacy/admin/home", findings=finding,
                 findings_dir="docs/survey/legacy-vs-new/findings",
                 front_matter_extra="existing_owner: admin-parity")
    write_record(tmp_path, "legacy/errors/404", status="clean", findings=[],
                 findings_dir="docs/survey/legacy-vs-new/findings")

    out = run_script(
        "emit-parity-backlog.py",
        "docs/survey/legacy-vs-new/inventory.json",
        "docs/survey/legacy-vs-new/findings",
        "docs/backlog.md",
        "docs/survey/legacy-vs-new/unit-manifest.json",
        repo=tmp_path,
    )

    backlog = (tmp_path / "docs/backlog.md").read_text()
    assert out["bullet_count"] == 1
    assert "[legacy-parity-auth-sign-in]" in backlog
    assert "legacy-parity-admin-home" not in backlog
    assert "legacy-parity-errors-404" not in backlog
