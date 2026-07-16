"""Tests for validate-knowledge.py — focus: the record enrichments are additive (non-breaking).

The enriched record adds `journeys[]` and per-component `chromeContext` + `feedbackKind`.
These must validate cleanly (the schema allows them; the validator must not reject them), so the
feature-doc/journey grounding can be recorded without failing the knowledge gate.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml
from conftest import run_script


def _write_record(repo: Path, record: dict, rel: str = "docs/knowledge/area/surf.json") -> str:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(record), encoding="utf-8")
    return rel


def _write_record_md(repo: Path, record: dict, *, body: str = "",
                     rel: str = "docs/knowledge/area/surf.md") -> str:
    """Write a record in the new Markdown + YAML front-matter form."""
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{yaml.safe_dump(record)}---\n\n{body}", encoding="utf-8")
    return rel


def test_md_frontmatter_record_passes(tmp_path):
    rel = _write_record_md(tmp_path, {
        "surface": "area/surf",
        "route": "/surf",
        "old": [{"name": "Save button", "dataSource": {"kind": "api", "endpoint": "POST /save"},
                 "feedbackKind": "transient"}],
        "journeys": [{"id": "edit-save", "name": "Edit and save", "steps": ["open", "save"]}],
    }, body="# Surface knowledge: area/surf\n\n## Components\n\n### Save button\n")
    out = run_script("validate-knowledge.py", rel, repo=tmp_path)
    assert out["knowledge_ok"] == "yes", out["knowledge_errors"]


def test_md_unclosed_frontmatter_fails(tmp_path):
    p = tmp_path / "docs/knowledge/area/surf.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("---\nsurface: area/surf\n", encoding="utf-8")  # no closing ---
    out = run_script("validate-knowledge.py", "docs/knowledge/area/surf.md", repo=tmp_path)
    assert out["knowledge_ok"] == "no"
    assert "front-matter" in out["knowledge_errors"]


def test_baseline_record_passes(tmp_path):
    rel = _write_record(tmp_path, {
        "surface": "area/surf",
        "new": [{"name": "Save button", "dataSource": {"kind": "api", "endpoint": "POST /save"}}],
    })
    out = run_script("validate-knowledge.py", rel, repo=tmp_path)
    assert out["knowledge_ok"] == "yes", out["knowledge_errors"]


def test_enriched_record_with_journeys_chrome_transient_passes(tmp_path):
    rel = _write_record(tmp_path, {
        "surface": "area/surf",
        "route": "/surf",
        "old": [
            {"name": "Save button", "dataSource": {"kind": "api", "endpoint": "POST /save"},
             "feedbackKind": "transient",
             "chromeContext": {"presentOn": ["editor"], "absentOn": ["list"]}},
        ],
        "journeys": [
            {"id": "edit-save", "name": "Edit and save a value", "surface": "area/surf",
             "steps": ["open editor", "change value", "save", "see persisted on reload"]},
        ],
        "provenance": {"sourcesRead": ["docs/features/area/surf.md"], "iteration": 1},
    })
    out = run_script("validate-knowledge.py", rel, repo=tmp_path)
    assert out["knowledge_ok"] == "yes", out["knowledge_errors"]
