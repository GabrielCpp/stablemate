"""Tests for append-backlog-item.py — the coder→backlog filer.

Subprocess tests (AGENT_REPO_DIR sandbox), mirroring the script's role as a best-effort
drain node: it must never exit non-zero, must enforce the `- [id] …` format contract,
de-duplicate against existing ids, place items under a named section when present, and
no-op cleanly when there is nothing to do or no backlog file.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "append-backlog-item.py"
SPEC_DIR = "docs/specs/s-1"


def _run(repo: Path, spec_dir: str = SPEC_DIR) -> dict:
    env = dict(os.environ, AGENT_REPO_DIR=str(repo))
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), spec_dir],
        capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, f"non-zero exit\nstderr:\n{proc.stderr}"
    return json.loads(proc.stdout)


def _items(repo: Path, items: list[dict]) -> None:
    p = repo / SPEC_DIR / "backlog-items.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(items), encoding="utf-8")


def _backlog(repo: Path, text: str) -> Path:
    p = repo / "docs" / "backlog.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_no_items_file_is_noop(tmp_path):
    _backlog(tmp_path, "# Backlog\n")
    out = _run(tmp_path)
    assert out["backlog_items_appended"] == 0


def test_appends_well_formed_bullet_under_section(tmp_path):
    bl = _backlog(tmp_path, "# Backlog\n\n## Projects\n\n- [existing] do existing\n\n## Admin\n")
    _items(tmp_path, [
        {"id": "section-tree-rebuild", "description": "BUG: section tree renders blank",
         "section": "## Projects"},
    ])
    out = _run(tmp_path)
    assert out["backlog_items_appended"] == 1
    body = bl.read_text()
    assert "- [section-tree-rebuild] BUG: section tree renders blank" in body
    # placed inside the Projects section (before the Admin heading)
    assert body.index("section-tree-rebuild") < body.index("## Admin")


def test_dedupes_against_existing_id(tmp_path):
    bl = _backlog(tmp_path, "# Backlog\n\n## Projects\n\n- [dup] already filed\n")
    _items(tmp_path, [{"id": "dup", "description": "filed again", "section": "## Projects"}])
    out = _run(tmp_path)
    assert out["backlog_items_appended"] == 0
    assert out["backlog_items_skipped"] == 1
    assert bl.read_text().count("[dup]") == 1


def test_dedupes_same_text_under_fresh_id(tmp_path):
    # A copy-paste re-file under a new id (signal 2: normalized description text).
    bl = _backlog(tmp_path, "# Backlog\n\n## Filed by coder\n\n- [orig] Fix the broken thing now.\n")
    _items(tmp_path, [{"id": "reworded-id", "description": "Fix the broken thing now.  "}])
    out = _run(tmp_path)
    assert out["backlog_items_appended"] == 0
    assert out["backlog_items_skipped"] == 1
    assert "reworded-id" not in bl.read_text()


def test_dedupes_word_permuted_id(tmp_path):
    # A word-permuted re-file of the same handle (signal 3: id-token-set), even with
    # differently-worded descriptions.
    _backlog(tmp_path, "# Backlog\n\n## Filed by coder\n\n"
                       "- [projects-new-cold-navigation-loses-route-match] A cold nav loses the match.\n")
    _items(tmp_path, [{"id": "cold-navigation-projects-new-loses-route-match",
                       "description": "A direct load loses the route match."}])
    out = _run(tmp_path)
    assert out["backlog_items_appended"] == 0
    assert out["backlog_items_skipped"] == 1


def test_does_not_merge_items_sharing_some_words(tmp_path):
    # Precision guard: two genuinely-distinct gaps that share several words (and topic) must
    # BOTH be filed — the dedup is exact-match, never fuzzy. Regression against over-merging.
    bl = _backlog(tmp_path, "# Backlog\n\n## Filed by coder\n\n"
                            "- [mysql-test-collection-assoc-fixture-gap-choice-fields] "
                            "Missing project_container_collection_assoc rows for choice fields.\n")
    _items(tmp_path, [{"id": "translation-table-missing-fr-rows-choice-fields-and-options",
                       "description": "Missing fr-locale translation rows for choice fields and options."}])
    out = _run(tmp_path)
    assert out["backlog_items_appended"] == 1
    assert "translation-table-missing-fr-rows-choice-fields-and-options" in bl.read_text()


def test_dedupes_new_signals_within_batch(tmp_path):
    # Signals 2 and 3 also de-dup within a single batch, not just against the backlog.
    _backlog(tmp_path, "# Backlog\n")
    _items(tmp_path, [
        {"id": "a-b-c", "description": "same underlying defect"},
        {"id": "c-b-a", "description": "worded differently"},      # id-token-set dup of a-b-c
        {"id": "totally-different", "description": "same underlying defect"},  # text dup of #1
    ])
    out = _run(tmp_path)
    assert out["backlog_items_appended"] == 1
    assert out["backlog_items_skipped"] == 2


def test_refile_of_blocked_item_is_deduped(tmp_path):
    # A blocked item keeps its bullet (annotated) so a re-file of its exact text still de-dups
    # against it — the (blocked: ...) suffix is stripped before comparing.
    _backlog(tmp_path, "# Backlog\n\n## Filed by coder\n\n"
                       "- [stuck] Do the hard thing. (blocked: QA still failing after one retry)\n")
    _items(tmp_path, [{"id": "do-the-hard-thing", "description": "Do the hard thing."}])
    out = _run(tmp_path)
    assert out["backlog_items_appended"] == 0
    assert out["backlog_items_skipped"] == 1


def test_dedupes_within_batch(tmp_path):
    bl = _backlog(tmp_path, "# Backlog\n")
    _items(tmp_path, [
        {"id": "same", "description": "first"},
        {"id": "same", "description": "second"},
    ])
    out = _run(tmp_path)
    assert out["backlog_items_appended"] == 1
    assert bl.read_text().count("[same]") == 1


def test_unknown_section_falls_back_to_filed_heading(tmp_path):
    bl = _backlog(tmp_path, "# Backlog\n\n## Projects\n")
    _items(tmp_path, [{"id": "x", "description": "do x", "section": "## Nonexistent"}])
    out = _run(tmp_path)
    assert out["backlog_items_appended"] == 1
    body = bl.read_text()
    assert "## Filed by coder" in body and "- [x] do x" in body


def test_id_is_sanitized_to_kebab(tmp_path):
    bl = _backlog(tmp_path, "# Backlog\n")
    _items(tmp_path, [{"id": "Section Tree!! Blank", "description": "do it"}])
    out = _run(tmp_path)
    assert out["backlog_items_appended"] == 1
    assert "- [section-tree-blank] do it" in bl.read_text()


def test_invalid_item_skipped(tmp_path):
    _backlog(tmp_path, "# Backlog\n")
    _items(tmp_path, [{"id": "", "description": "no id"}, {"id": "ok"}])  # both invalid
    out = _run(tmp_path)
    assert out["backlog_items_appended"] == 0
    assert out["backlog_items_skipped"] == 2


def test_creates_backlog_when_missing(tmp_path):
    # coder-only repo with no author backlog yet — the filer creates a minimal backlog and files
    # the item under "## Filed by coder" rather than dropping it.
    backlog = tmp_path / "docs" / "backlog.md"
    _items(tmp_path, [{"id": "x", "description": "do x"}])
    out = _run(tmp_path)
    assert out["backlog_items_appended"] == 1
    assert backlog.is_file()
    body = backlog.read_text()
    assert "## Filed by coder" in body and "- [x] do x" in body


def test_items_file_removed_after_successful_drain(tmp_path):
    # Once reconciled into an existing backlog, the items file is removed so the same items
    # are never re-filed and no stale artifact lingers in the spec dir.
    _backlog(tmp_path, "# Backlog\n")
    items_file = tmp_path / SPEC_DIR / "backlog-items.json"
    _items(tmp_path, [{"id": "x", "description": "do x"}])
    out = _run(tmp_path)
    assert out["backlog_items_appended"] == 1
    assert not items_file.exists()


def test_items_file_removed_even_when_all_duplicates(tmp_path):
    # An all-duplicate batch is still fully reconciled (the ids are already in the backlog),
    # so the redundant items file is removed too — reruns must not pile it back up.
    _backlog(tmp_path, "# Backlog\n\n## Projects\n\n- [dup] already filed\n")
    items_file = tmp_path / SPEC_DIR / "backlog-items.json"
    _items(tmp_path, [{"id": "dup", "description": "filed again", "section": "## Projects"}])
    out = _run(tmp_path)
    assert out["backlog_items_appended"] == 0
    assert out["backlog_items_skipped"] == 1
    assert not items_file.exists()


def test_items_file_removed_after_creating_backlog(tmp_path):
    # When the backlog is created on the fly, the items are still captured, so the items file
    # is removed just like the normal drain path.
    items_file = tmp_path / SPEC_DIR / "backlog-items.json"
    _items(tmp_path, [{"id": "x", "description": "do x"}])
    out = _run(tmp_path)
    assert out["backlog_items_appended"] == 1
    assert not items_file.exists()
