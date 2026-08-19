"""`farrier doctor` reports what a repo's `agents.yml` leaves a workflow unable to do.

The behaviour under test is the one that makes the command worth having: an undeclared gate
is silent at run time by design, so the only place a repo can find out it adopted none is a
command that says so. It warns and exits 0 — not adopting a gate is a choice, and a doctor
that failed on a choice would be a doctor nobody runs.
"""
from __future__ import annotations

from pathlib import Path

from farrier.cli import main
from farrier.doctor import diagnose


def _write(repo: Path, body: str) -> Path:
    (repo / "agents.yml").write_text(body, encoding="utf-8")
    return repo


def test_a_repo_with_no_services_block_is_warned_that_nothing_is_gated(tmp_path: Path) -> None:
    _write(tmp_path, "repo:\n  name: acme\n")

    findings = diagnose(tmp_path)

    assert [f.level for f in findings] == ["warning"] * len(findings)
    assert any("no services: block" in f.message for f in findings)


def test_a_partially_declared_service_is_warned_about_the_missing_gate(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "workspace:\n"
        "  service_roots: [api]\n"
        "  service_markers: [go.mod]\n"
        "services:\n"
        "  api: {lint: 'golangci-lint run'}\n",
    )

    findings = diagnose(tmp_path)

    assert len(findings) == 1
    assert "declares no test command" in findings[0].message


def test_a_fully_declared_repo_has_nothing_to_report(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "workspace:\n"
        "  service_roots: [api]\n"
        "  service_markers: [go.mod]\n"
        "services:\n"
        "  api: {lint: 'golangci-lint run', test: 'go test ./...'}\n",
    )

    assert diagnose(tmp_path) == []


def test_the_legacy_lint_map_counts_as_an_adopted_lint_gate(tmp_path: Path) -> None:
    """A repo already running the old map is not told to adopt what it has adopted."""
    _write(
        tmp_path,
        "workspace:\n"
        "  service_roots: [api]\n"
        "  service_markers: [go.mod]\n"
        "lint:\n"
        "  api: sh lint.sh\n"
        "services:\n"
        "  api: {test: 'go test ./...'}\n",
    )

    assert diagnose(tmp_path) == []


def test_a_missing_agents_yml_is_the_one_error(tmp_path: Path) -> None:
    findings = diagnose(tmp_path)

    assert [f.level for f in findings] == ["error"]
    assert main(["doctor", "--repo", str(tmp_path)]) == 1


def test_warnings_alone_exit_zero(tmp_path: Path, capsys) -> None:
    _write(tmp_path, "repo:\n  name: acme\n")

    assert main(["doctor", "--repo", str(tmp_path)]) == 0
    assert "warning:" in capsys.readouterr().out
