"""validate-record.py — the hard per-record validator."""
from __future__ import annotations

from tests.conftest import init_repo, run_script, write_record

FINDINGS = "docs/survey/findings"


def validate(repo, unit_id, rel_path=None):
    rel = rel_path or f"{FINDINGS}/{unit_id.replace('/', '-').lower()}.md"
    return run_script("validate-record.py", rel, unit_id, repo=repo)


def test_valid_assessed_record_passes(tmp_path):
    init_repo(tmp_path)
    write_record(tmp_path, "src/a")
    out = validate(tmp_path, "src/a")
    assert out["record_ok"] == "yes", out["record_errors"]


def test_valid_clean_and_blocked_records_pass(tmp_path):
    init_repo(tmp_path)
    write_record(tmp_path, "src/clean", status="clean", findings=[])
    write_record(tmp_path, "src/blocked", status="blocked", findings=[],
                 open_gaps=["needs prod credentials"])
    assert validate(tmp_path, "src/clean")["record_ok"] == "yes"
    assert validate(tmp_path, "src/blocked")["record_ok"] == "yes"


def test_missing_record_fails(tmp_path):
    init_repo(tmp_path)
    out = validate(tmp_path, "src/a")
    assert out["record_ok"] == "no"
    assert "missing" in out["record_errors"]


def test_unit_mismatch_fails(tmp_path):
    init_repo(tmp_path)
    rec = write_record(tmp_path, "src/other")
    out = run_script("validate-record.py", str(rec.relative_to(tmp_path)), "src/a",
                     repo=tmp_path)
    assert out["record_ok"] == "no"
    assert "must describe its own inventory unit" in out["record_errors"]


def test_assessed_without_findings_fails(tmp_path):
    init_repo(tmp_path)
    write_record(tmp_path, "src/a", status="assessed", findings=[])
    out = validate(tmp_path, "src/a")
    assert out["record_ok"] == "no"
    assert "use `clean`" in out["record_errors"]


def test_clean_with_findings_is_a_contradiction(tmp_path):
    init_repo(tmp_path)
    write_record(tmp_path, "src/a", status="clean",
                 findings=[{"description": "d", "remediation_pattern": "p",
                            "effort": "small", "evidence": "e:1"}])
    out = validate(tmp_path, "src/a")
    assert out["record_ok"] == "no"
    assert "contradiction" in out["record_errors"]


def test_blocked_without_open_gaps_fails(tmp_path):
    init_repo(tmp_path)
    write_record(tmp_path, "src/a", status="blocked", findings=[])
    out = validate(tmp_path, "src/a")
    assert out["record_ok"] == "no"
    assert "openGaps" in out["record_errors"]


def test_incomplete_finding_fields_fail(tmp_path):
    init_repo(tmp_path)
    write_record(tmp_path, "src/a", findings=[
        {"description": "", "remediation_pattern": "Bad Slug!",
         "effort": "huge", "evidence": ""},
    ])
    out = validate(tmp_path, "src/a")
    assert out["record_ok"] == "no"
    errs = out["record_errors"]
    assert "description" in errs
    assert "kebab-case" in errs
    assert "effort 'huge'" in errs
    assert "evidence" in errs


def test_malformed_yaml_fails_cleanly(tmp_path):
    init_repo(tmp_path)
    rec = tmp_path / FINDINGS / "src-a.md"
    rec.parent.mkdir(parents=True)
    rec.write_text("---\nunit: [unclosed\n---\n", encoding="utf-8")
    out = run_script("validate-record.py", f"{FINDINGS}/src-a.md", "src/a", repo=tmp_path)
    assert out["record_ok"] == "no"
    assert "could not be parsed" in out["record_errors"]


def test_disposition_only_valid_on_blocked(tmp_path):
    init_repo(tmp_path)
    write_record(tmp_path, "src/a", disposition="accepted")
    out = validate(tmp_path, "src/a")
    assert out["record_ok"] == "no"
    assert "only makes sense on a `blocked` record" in out["record_errors"]

    write_record(tmp_path, "src/b", status="blocked", findings=[],
                 open_gaps=["gap"], disposition="accepted")
    assert validate(tmp_path, "src/b")["record_ok"] == "yes"
