"""`ostler qa assess`: every owed obligation of one book accounted for exactly once."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from conftest import ostler_process, write
from ostler.qa.assessment import assess, cmd_assess, contract_fingerprint, render, to_json

BOOK = "docs/services/tool"


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _repo(root: Path) -> Path:
    (root / BOOK).mkdir(parents=True)
    _git(root, "init")
    _git(root, "config", "user.email", "qa@example.com")
    _git(root, "config", "user.name", "QA")
    return root


def _commit(root: Path) -> None:
    _git(root, "add", ".")
    _git(root, "commit", "-m", "base", "--allow-empty")


def _hello_page(extra: str = "") -> str:
    return (
        "---\ntype: cli\nslug: tool\ntitle: tool\n---\n# tool\n\n- binary: tool\n\n"
        "## Commands\n\n"
        "### hello\n"
        "- usage: `tool hello`\n"
        '- run: invoke(argv=["hello"])\n'
        "- does: prints its greeting on stdout.\n"
        '  - verify: stdout(text="hello world")\n'
        "  - fixture: none, because the greeting does not depend on any world\n"
        + extra
    )


def _concept_page() -> str:
    return "---\ntype: concept\ntitle: Greeting\n---\n# Greeting\n\nThe greeting is a definition, not a surface.\n"


def test_a_supported_cli_surface_is_incomplete_without_evidence(tmp_path: Path):
    root = _repo(tmp_path)
    write(root / BOOK / "tool.md", _hello_page())
    write(root / BOOK / "greeting.md", _concept_page())
    _commit(root)

    result = cmd_assess(root, book=BOOK)

    assert not result.ok
    assert result.status == "incomplete"
    data = result.data
    assert data["capabilities_complete"] is True
    assert data["sensitivity_complete"] is True
    assert data["evidence_complete"] is False
    assert data["complete"] is False
    required = [row for row in data["obligations"] if row["required"]]
    assert required, "the hello command owes at least one obligation"
    owing = [row for row in required if row["declares_checks"]]
    assert all(row["evidence"] == "not-run" for row in owing)
    assert all(row["capability"] == "complete" for row in required)
    assert all(row["sensitivity"] == "sensitive" for row in owing)
    contracts = [row for row in required if not row["declares_checks"]]
    assert contracts and all(row["evidence"] == "not-declared" for row in contracts)
    assert data["excluded_count"] >= 1, "the concept page owes no live evidence"


def test_a_missing_check_and_a_missing_fixture_stay_in_the_denominator(tmp_path: Path):
    root = _repo(tmp_path)
    write(root / BOOK / "tool.md", (
        "---\ntype: cli\nslug: tool\ntitle: tool\n---\n# tool\n\n- binary: tool\n\n"
        "## Commands\n\n"
        "### bare\n"
        "- usage: `tool bare`\n"
        "- does: declares no check, so nothing can prove it.\n"
        "### unarranged\n"
        "- usage: `tool unarranged`\n"
        '- run: invoke(argv=["unarranged"])\n'
        "- does: arranges nothing and does not say it needs nothing.\n"
        '  - verify: stdout(text="x")\n'
    ))
    _commit(root)

    data = cmd_assess(root, book=BOOK).data
    required = [row for row in data["obligations"] if row["required"]]
    assert data["required_count"] == len(required)
    gapped = {row["id"]: row for row in required if row["gaps"]}
    causes = {gap["code"] for row in gapped.values() for gap in row["gaps"]}
    assert "no-verify-declared" in causes
    assert "unarranged-scenario" in causes
    assert all(gap["owner"] == "book" for row in gapped.values() for gap in row["gaps"])
    # Neither fell out of the denominator: every required row is reported exactly once.
    ids = [row["id"] for row in data["obligations"]]
    assert len(ids) == len(set(ids))


def test_an_empty_scope_refuses(tmp_path: Path):
    root = _repo(tmp_path)
    write(root / BOOK / "tool.md", _hello_page())
    _commit(root)

    missing = cmd_assess(root, book="docs/services/nope")
    assert missing.status == "invalid" and not missing.ok
    empty = cmd_assess(root, book="docs/services/empty")
    (root / "docs/services/empty").mkdir(parents=True)
    assert empty.status == "invalid"
    blank = cmd_assess(root, book="")
    assert blank.status == "invalid"


def test_human_and_json_views_account_for_the_same_ids(tmp_path: Path):
    root = _repo(tmp_path)
    write(root / BOOK / "tool.md", _hello_page())
    _commit(root)

    assessment = assess(root, book=BOOK)
    json_ids = {row["id"] for row in to_json(assessment)["obligations"]}
    text = render(assessment)
    for oid in json_ids:
        assert oid in text, f"the human view omits {oid}"
    assert {row.id for row in assessment.rows} == json_ids


def test_assessment_runs_no_product_command(tmp_path: Path):
    """The read-only invariant: no scenario runs, no fixture command executes."""
    root = _repo(tmp_path)
    write(root / BOOK / "tool.md", _hello_page(
        '- run: invoke(argv=["touch", "ran.txt"])\n'))
    sentinel = root / BOOK / "ran.txt"
    _commit(root)

    result = cmd_assess(root, book=BOOK)

    assert not sentinel.exists(), "assessment executed a product command"
    assert result.status in ("incomplete", "invalid")


def test_a_claim_edit_with_its_id_kept_moves_the_contract_fingerprint(tmp_path: Path):
    root = _repo(tmp_path)
    write(root / BOOK / "tool.md", _hello_page())
    _commit(root)
    before = contract_fingerprint(__import__("ostler.qa.context", fromlist=["book_context"]).book_context(root, books=[BOOK]))

    write(root / BOOK / "tool.md", _hello_page(
        "### hello\n"
        "- usage: `tool hello --loud`\n"
        '- run: invoke(argv=["hello", "--loud"])\n'
        "- does: prints its greeting louder.\n"
        '  - verify: stdout(text="HELLO WORLD")\n'
        "  - fixture: none, because loudness needs no world\n"))
    after = contract_fingerprint(__import__("ostler.qa.context", fromlist=["book_context"]).book_context(root, books=[BOOK]))

    assert before != after


def test_the_cli_reports_incomplete_with_exit_1_and_invalid_with_exit_2(tmp_path: Path):
    root = _repo(tmp_path)
    write(root / BOOK / "tool.md", _hello_page())
    _commit(root)

    done = ostler_process(root, "qa", "assess", "--book", BOOK, "--json")
    assert done.returncode == 1, done.stdout
    payload = json.loads(done.stdout)
    assert payload["complete"] is False
    assert payload["capabilities_complete"] is True

    refused = ostler_process(root, "qa", "assess", "--book", "docs/services/nope")
    assert refused.returncode == 2
