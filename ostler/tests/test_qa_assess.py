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
        "- does: prints its greeting on stdout.\n"
        '  - run: invoke(argv=["hello"])\n'
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


# --- slice 2: the contract snapshot and recorded run evidence ---

from ostler.qa import cmd_run  # noqa: E402
from ostler.qa.compile import annotate_deferred_obligations, compile_plan  # noqa: E402
from ostler.qa.context import build_context, write_context  # noqa: E402

GREET_BOOK = "docs/services/tool"


def _greet_page(verify: str = 'stdout(text="hello")') -> str:
    return (
        "---\ntype: cli\nslug: tool\ntitle: tool\n---\n# tool\n\n- binary: tool\n\n"
        "## Commands\n\n"
        "### greet\n"
        "- usage: `tool greet`\n"
        "- does: says its greeting on stdout.\n"
        '  - run: invoke(argv=["hello"])\n'
        f"  - verify: {verify}\n"
        "  - fixture: none, because nothing is seeded\n"
    )


def _experiment_repo(tmp_path: Path, monkeypatch, verify: str = 'stdout(text="hello")') -> tuple[Path, Path]:
    """A repo whose whole-book context, compiled plan and executed run all agree."""
    root = _repo(tmp_path)
    write(root / GREET_BOOK / "tool.md", _greet_page(verify))
    write(root / GREET_BOOK / "greeting.md", _concept_page())
    write(root / "agents.yml", "qa:\n  tools:\n    - tool\n")
    write(root / "qa.toml", '[qa_tools.tool]\ncommand = "echo"\ndescription = "echoes its arguments"\n')
    write(root / ".gitignore", "art/\n")
    monkeypatch.setenv("STABLEMATE_CONFIG", str(root / "qa.toml"))
    _commit(root)
    base = _git(root, "rev-parse", "HEAD")
    context = build_context(root, base=base, whole_book=True, books=[GREET_BOOK])
    annotate_deferred_obligations(context, story="s1")
    spec_dir = root / "art/specs/s1"
    write_context(context, spec_dir)
    plan = compile_plan(context, story="s1")
    write(spec_dir / "qa_plan.py", plan)
    result = cmd_run(spec_dir / "qa_plan.py", spec_dir, root=root)
    assert result.status in ("passed", "failed"), result.message
    return root, spec_dir


def test_a_surface_with_a_matching_run_is_complete(tmp_path: Path, monkeypatch) -> None:
    root, spec_dir = _experiment_repo(tmp_path, monkeypatch)

    result = cmd_assess(root, book=GREET_BOOK, spec_dir=spec_dir)

    assert result.ok, result.message
    assert result.status == "complete"
    data = result.data
    assert data["complete"] is True
    assert data["evidence_complete"] is True
    assert data["evidence"]["applicability"] == "applicable"
    owing = [row for row in data["obligations"] if row["required"] and row["declares_checks"]]
    assert owing and all(row["evidence"] == "complete" for row in owing)


def test_a_claim_edit_with_its_id_kept_makes_the_run_evidence_stale(tmp_path: Path, monkeypatch) -> None:
    root, spec_dir = _experiment_repo(tmp_path, monkeypatch)

    write(root / GREET_BOOK / "tool.md", _greet_page('stdout(text="hello there")'))
    result = cmd_assess(root, book=GREET_BOOK, spec_dir=spec_dir)

    assert not result.ok
    assert result.status == "incomplete"
    assert result.data["evidence"]["applicability"] == "stale"
    owing = [row for row in result.data["obligations"] if row["required"] and row["declares_checks"]]
    assert all(row["evidence"] == "stale" for row in owing)


def test_a_failed_run_cannot_pass(tmp_path: Path, monkeypatch) -> None:
    root, spec_dir = _experiment_repo(tmp_path, monkeypatch, verify='stdout(text="goodbye")')

    result = cmd_assess(root, book=GREET_BOOK, spec_dir=spec_dir)

    assert not result.ok
    owing = [row for row in result.data["obligations"]
             if row["id"].endswith(":does:1") and row["declares_checks"]]
    assert owing and all(row["evidence"] == "unavailable" for row in owing)


def test_legacy_evidence_without_a_fingerprint_cannot_pass(tmp_path: Path, monkeypatch) -> None:
    root, spec_dir = _experiment_repo(tmp_path, monkeypatch)
    evidence_path = spec_dir / "qa-evidence.json"
    legacy = json.loads(evidence_path.read_text(encoding="utf-8"))
    legacy.pop("contractFingerprint", None)
    legacy.pop("fingerprintVersion", None)
    evidence_path.write_text(json.dumps(legacy), encoding="utf-8")

    result = cmd_assess(root, book=GREET_BOOK, spec_dir=spec_dir)

    assert not result.ok
    assert result.data["evidence"]["applicability"] == "unusable"


def test_an_interrupted_run_without_its_ledger_cannot_pass(tmp_path: Path, monkeypatch) -> None:
    root, spec_dir = _experiment_repo(tmp_path, monkeypatch)
    import shutil
    shutil.rmtree(spec_dir / "qa")

    result = cmd_assess(root, book=GREET_BOOK, spec_dir=spec_dir)

    assert not result.ok
    assert result.data["evidence"]["applicability"] == "unusable"


def test_malformed_and_duplicated_evidence_cannot_pass(tmp_path: Path, monkeypatch) -> None:
    root, spec_dir = _experiment_repo(tmp_path, monkeypatch)
    (spec_dir / "qa-evidence.json").write_text("{not json", encoding="utf-8")
    malformed = cmd_assess(root, book=GREET_BOOK, spec_dir=spec_dir)
    assert malformed.data["evidence"]["applicability"] == "unusable"

    root2, spec_dir2 = _experiment_repo(tmp_path / "dup", monkeypatch)
    evidence_path = spec_dir2 / "qa-evidence.json"
    data = json.loads(evidence_path.read_text(encoding="utf-8"))
    data["obligations"] = data["obligations"] + data["obligations"][:1]
    evidence_path.write_text(json.dumps(data), encoding="utf-8")
    duplicated = cmd_assess(root2, book=GREET_BOOK, spec_dir=spec_dir2)
    assert duplicated.data["evidence"]["applicability"] == "unusable"


def test_a_run_that_proves_only_a_subset_cannot_complete_the_surface(tmp_path: Path, monkeypatch) -> None:
    root, _ = _experiment_repo(tmp_path, monkeypatch)
    # A second spec whose packet owes only the greet claim: a diff-selected subset.
    subset_dir = root / "art/specs/subset"
    context = build_context(root, base=_git(root, "rev-parse", "HEAD"), whole_book=True,
                            books=[GREET_BOOK])
    greet = next(row for row in context["obligations"]
                 if row["id"] == "okf:docs/services/tool/tool.md#greet:does:1")
    write_context({**context, "obligations": [greet]}, subset_dir)
    plan = compile_plan({**context, "obligations": [greet]}, story="subset")
    write(subset_dir / "qa_plan.py", plan)
    result = cmd_run(subset_dir / "qa_plan.py", subset_dir, root=root)
    assert result.ok, result.message

    assessed = cmd_assess(root, book=GREET_BOOK, spec_dir=subset_dir)

    assert not assessed.ok
    assert assessed.data["evidence"]["applicability"] == "stale"


# --- slice 3: gap ownership, doctor findings in scope, the blocking policy ---

from ostler.qa.compile import GAP_KINDS  # noqa: E402
from ostler.qa.gap_owner import BOOK as OWNER_BOOK, ENVIRONMENT, TOOLING, gap_owner  # noqa: E402


def test_every_compile_gap_kind_is_classified_by_owner() -> None:
    """The owner table is exhaustive: an unclassified kind must fail the assessment, never pass it."""
    unclassified = sorted(GAP_KINDS - {kind for kind in GAP_KINDS if gap_owner(kind)})
    assert unclassified == []


def test_a_missing_declaration_routes_to_the_book_author(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    write(root / BOOK / "tool.md", (
        "---\ntype: cli\nslug: tool\ntitle: tool\n---\n# tool\n\n- binary: tool\n\n"
        "## Commands\n\n### bare\n- usage: `tool bare`\n- does: declares nothing observable.\n"))
    _commit(root)

    data = cmd_assess(root, book=BOOK).data
    gaps = [gap for row in data["obligations"] for gap in row["gaps"]]
    assert gaps and all(gap["owner"] == OWNER_BOOK for gap in gaps)


def test_a_capture_the_cli_builder_cannot_emit_routes_to_tooling(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    write(root / BOOK / "tool.md", (
        "---\ntype: cli\nslug: tool\ntitle: tool\n---\n# tool\n\n- binary: tool\n\n"
        "## Commands\n\n### greet\n"
        "- usage: `tool greet`\n"
        '- run: invoke(argv=["hello"])\n'
        "- does: says hello and names the capture nothing can emit.\n"
        '  - verify: stdout(text="hello")\n'
        "  - fixture: none, because nothing is seeded\n"
        "- capture: greeting from stdout\n"))
    _commit(root)

    data = cmd_assess(root, book=BOOK).data
    gaps = [gap for row in data["obligations"] for gap in row["gaps"]]
    tooling = [gap for gap in gaps if gap["owner"] == TOOLING]
    assert any(gap["code"] == "uncaptured-declaration" for gap in tooling)
    # the gap carries its address and remedy, not just its cause
    assert all(gap["path"] and gap["remedy"] for gap in gaps)


def _ops_book(root: Path, health: str) -> None:
    write(root / BOOK / "ops/test.md", (
        "---\ntype: environment\ntitle: Test\n---\n\n# Test\n\n"
        "- sharing: per-run\n- addresses:\n  - `gateway`: the front door\n"))
    write(root / BOOK / "ops/web.md", (
        "---\ntype: runbook\ntitle: Web\n---\n\n# Web\n\n- driver: web\n"
        "- environment: [Test](test.md)\n- entry-url: {gateway}\n- stop: make down\n\n"
        f"## Steps\n\n### serve\n\n- kind: service\n- run: make copy\n- health: {health}\n"))


def test_a_missing_runtime_input_routes_to_the_environment(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _ops_book(root, health="curl -fsS {api}/health")
    _commit(root)

    result = cmd_assess(root, book=BOOK)
    data = result.data

    assert not result.ok
    assert data["structure_complete"] is False
    finding = next(f for f in data["doctor_findings"] if f["code"] == "runbook-unknown-address")
    assert finding["owner"] == ENVIRONMENT
    assert finding["path"].startswith(BOOK)


def test_a_warning_severity_finding_does_not_block_the_structure_verdict(tmp_path: Path) -> None:
    """The finding policy blocks on error-severity findings; warnings stay visible without blocking."""
    root = _repo(tmp_path)
    write(root / BOOK / "tool.md", _greet_page().replace(
        '- verify: stdout(text="hello")',
        '- verify: stdout(matches="((a*)*)*$")'))
    _commit(root)

    data = cmd_assess(root, book=BOOK).data
    assert any(f["severity"] == "warn" for f in data["doctor_findings"])
    assert data["structure_complete"] is True


def test_gap_counts_group_by_cause_keeping_per_gap_detail(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    write(root / BOOK / "tool.md", _greet_page().replace(
        "- does: says its greeting on stdout.\n",
        "- does: says its greeting on stdout.\n- does: a second claim nobody proves.\n"))
    _commit(root)

    data = cmd_assess(root, book=BOOK).data
    # three rows carry the cause: the unproven claim, and the two discharged contracts
    assert data["gap_counts"].get("no-verify-declared") == 3
    detail = [gap for row in data["obligations"] for gap in row["gaps"]
              if gap["code"] == "no-verify-declared"]
    assert all(gap["line"] > 0 and "verify:" in gap["remedy"] for gap in detail)
