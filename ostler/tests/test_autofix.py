"""`ostler autofix` — deterministic repair of shape-detectable format drift.

The one fix under test: a `verify:` bullet holding `path::symbol` test citations — the
pre-split spelling — moves to `tests:`. The predicate must prove the value is a citation
run before touching it; everything it cannot prove stays for doctor and judgment.
"""

from __future__ import annotations

from pathlib import Path

from ostler import autofix
from ostler.cli import main

from conftest import write


def endpoint_doc(verify_value: str) -> str:
    return (
        "---\ntype: api\nslug: s\ntitle: T\n---\n# T\n\n"
        "## Endpoints\n\n### submit\n"
        "- route: `POST /x`\n"
        f"- verify: {verify_value}\n"
    )


def test_drifted_verify_becomes_tests():
    out = autofix.fix_text(endpoint_doc(
        "`api-service/internal/account/account_service_test.go::Test_Create`"))
    assert ("- tests: `api-service/internal/account/account_service_test.go::Test_Create`"
            in out)
    assert "- verify:" not in out


def test_multi_ref_citation_run_moves_whole():
    out = autofix.fix_text(endpoint_doc(
        "`web-app/app/routes/home.test.tsx::renders`, `web-app/app/routes/home.test.tsx::submits`"))
    assert out.count("- tests: `web-app/app/routes/home.test.tsx::renders`, "
                     "`web-app/app/routes/home.test.tsx::submits`") == 1
    assert "- verify:" not in out


def test_parsing_check_is_never_touched():
    text = endpoint_doc('http_status(201, path="/x")')
    assert autofix.fix_text(text) == text


def test_prose_verify_is_left_for_judgment():
    text = endpoint_doc("the row appears in the table after saving")
    assert autofix.fix_text(text) == text


def test_ref_without_file_extension_is_left_alone():
    # `api-service/internal/service` could be a package or a stray identifier — not provably
    # a test file, so not provably the split's path half.
    text = endpoint_doc("`api-service/internal/service::Test_Create`")
    assert autofix.fix_text(text) == text


def test_type_without_tests_key_is_left_alone():
    # A `step`'s `verify:` is a link, not a check, and the type declares no `tests:` —
    # there is nowhere provable to move the value to.
    text = (
        "---\ntype: server\nslug: s\ntitle: T\n---\n# T\n\n"
        "## Runbooks\n\n### boot\n- does:\n  - start\n\n"
        "## Steps\n\n### start\n"
        "- run: `make up`\n"
        "- verify: `scripts/smoke_test.py::test_up`\n"
    )
    assert autofix.fix_text(text) == text


def test_file_level_node_is_fixed_too():
    text = (
        "---\ntype: concept\nslug: c\ntitle: C\n---\n# C\n\n"
        "- semantics: holds the account ledger.\n"
        "- verify: `api-service/internal/ledger/ledger_test.go::Test_Balance`\n"
    )
    out = autofix.fix_text(text)
    assert "- tests: `api-service/internal/ledger/ledger_test.go::Test_Balance`" in out
    assert "- verify:" not in out


def test_idempotent():
    once = autofix.fix_text(endpoint_doc(
        "`api-service/internal/account/account_service_test.go::Test_Create`"))
    assert autofix.fix_text(once) == once


def test_clean_book_is_a_noop():
    text = (
        "---\ntype: api\nslug: s\ntitle: T\n---\n# T\n\n"
        "## Endpoints\n\n### submit\n"
        "- route: `POST /x`\n"
        '- verify: http_status(201, path="/x")\n'
        "- tests: `api-service/internal/account/account_service_test.go::Test_Create`\n"
    )
    assert autofix.fix_text(text) == text


def test_cli_check_then_write(repo: Path):
    p = repo / "docs/features/s.md"
    write(p, endpoint_doc("`api-service/internal/account/account_service_test.go::Test_Create`"))
    assert main(["-C", str(repo), "autofix", "--check"]) == 1
    assert p.read_text().count("- verify:") == 1        # --check never writes
    assert main(["-C", str(repo), "autofix"]) == 0
    assert "- tests:" in p.read_text()
    assert main(["-C", str(repo), "autofix", "--check"]) == 0
