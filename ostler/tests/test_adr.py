"""The Decision record: ``adr.propose`` writes ``adr/<id>.md`` and binds its evidence in one artifacts commit."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from ostler import adr, ids, register
from ostler._vendor.stablemate_core import config as core_config
from ostler.model import Graph, load
from ostler.result import Result


def artifacts() -> Path:
    return Path(os.environ["STABLEMATE_ARTIFACTS_DIR"]).resolve()


def git(*args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(artifacts()), *args], capture_output=True, text=True, check=True, timeout=30,
    )
    return done.stdout


def shelve(tmp_path: Path) -> tuple[Graph, list[str]]:
    core_config.ensure_artifacts_repo()
    graph = load(tmp_path)
    for record_id, repo, area in (
        ("acme-1", "web-app", "cart"),
        ("acme-2", "api-service", "billing"),
        ("acme-3", "api-service", "cart"),
    ):
        filing = register.file_record(
            graph, repo=repo, area=area, pattern="guard-the-total", summary=f"summary of {record_id}",
            filed_by="qa", record_id=record_id, body="The slice worked without it.",
        )
        assert filing.ok, filing.message
    register.commit(graph, [artifacts() / "backlog"], "chore: shelve")
    return load(tmp_path), ["acme-1", "acme-2", "acme-3"]


def propose(graph: Graph, evidence: list[str]) -> Result:
    return adr.propose(
        graph, title="Guard every total", context="Three records share a cause.",
        decision="Guard the total in one place.", consequences="One module owns the rule.",
        evidence=evidence,
    )


def record_text(graph: Graph, record_id: str) -> str:
    folder = register.locate(graph, record_id)
    assert folder is not None
    return (folder / register.RECORD_FILE).read_text(encoding="utf-8")


def test_three_records_yield_one_proposed_decision_with_repos_and_evidence(tmp_path: Path) -> None:
    graph, evidence = shelve(tmp_path)

    result = propose(graph, evidence)

    assert result.ok, result.message
    target = artifacts() / "adr" / f"{result.entity_id}.md"
    assert target.is_file()
    decision = adr.Decision.read(target)
    assert decision.status == "proposed"
    assert decision.repos == ["api-service", "web-app"]
    assert decision.evidence == evidence
    assert decision.id == result.entity_id
    text = target.read_text(encoding="utf-8")
    assert text.index("## Context") < text.index("## Decision") < text.index("## Consequences")
    assert "Guard the total in one place." in text


def test_each_record_carries_the_new_id_and_nothing_else_changed(tmp_path: Path) -> None:
    graph, evidence = shelve(tmp_path)
    before = {i: record_text(graph, i) for i in evidence}

    result = propose(graph, evidence)

    assert result.ok, result.message
    after = load(tmp_path)
    for record_id in evidence:
        assert record_text(after, record_id) == before[record_id].replace(
            "decision: ''", f"decision: {result.entity_id}")
        folder = register.locate(after, record_id)
        assert folder is not None
        record = register.Record.read(folder / register.RECORD_FILE)
        assert record.decision == result.entity_id
        assert record.status == "open"


def test_one_artifacts_commit_holds_the_adr_and_every_record(tmp_path: Path) -> None:
    graph, evidence = shelve(tmp_path)
    before = int(git("rev-list", "--count", "HEAD"))

    result = propose(graph, evidence)

    assert int(git("rev-list", "--count", "HEAD")) == before + 1
    assert git("log", "-1", "--format=%s").strip() == f"chore: propose {result.entity_id} from 3 records"
    assert sorted(git("show", "--name-only", "--format=", "HEAD").split()) == sorted([
        f"adr/{result.entity_id}.md",
        "backlog/web-app/cart/acme-1/record.md",
        "backlog/api-service/billing/acme-2/record.md",
        "backlog/api-service/cart/acme-3/record.md",
    ])


def test_no_evidence_is_refused(tmp_path: Path) -> None:
    graph, _ = shelve(tmp_path)

    result = propose(graph, [])

    assert not result.ok
    assert not (artifacts() / "adr").exists()


def test_an_unknown_evidence_id_is_refused_and_named_and_nothing_is_written(tmp_path: Path) -> None:
    graph, evidence = shelve(tmp_path)
    before = {i: record_text(graph, i) for i in evidence}
    head = git("rev-parse", "HEAD")

    result = propose(graph, [*evidence, "acme-404"])

    assert not result.ok and "acme-404" in result.message
    assert not list((artifacts() / "adr").glob("*.md"))
    assert {i: record_text(load(tmp_path), i) for i in evidence} == before
    assert git("rev-parse", "HEAD") == head


def test_a_record_bound_to_another_decision_is_refused_and_named(tmp_path: Path) -> None:
    graph, evidence = shelve(tmp_path)
    first = propose(graph, evidence[:2])
    assert first.ok, first.message
    graph = load(tmp_path)
    before = {i: record_text(graph, i) for i in evidence}
    head = git("rev-parse", "HEAD")

    result = propose(graph, evidence)

    assert not result.ok and "acme-1" in result.message
    assert [p.stem for p in (artifacts() / "adr").glob("*.md")] == [first.entity_id]
    assert {i: record_text(load(tmp_path), i) for i in evidence} == before
    assert git("rev-parse", "HEAD") == head


def test_the_minted_id_is_in_the_workspace_id_space(tmp_path: Path) -> None:
    graph, evidence = shelve(tmp_path)

    result = propose(graph, evidence)

    assert result.entity_id in ids.known(load(tmp_path))
    assert result.entity_id not in evidence


def test_a_failed_commit_restores_every_file_and_removes_the_adr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph, evidence = shelve(tmp_path)
    before = {i: record_text(graph, i) for i in evidence}

    def broken(*_args: object, **_kwargs: object) -> bool:
        raise subprocess.CalledProcessError(1, "git")

    monkeypatch.setattr(register, "commit", broken)
    result = propose(graph, evidence)

    assert not result.ok
    assert {i: record_text(load(tmp_path), i) for i in evidence} == before
    assert not list((artifacts() / "adr").glob("*.md"))


def test_decisions_lists_what_parsed_and_names_what_did_not(tmp_path: Path) -> None:
    graph, evidence = shelve(tmp_path)
    result = propose(graph, evidence)
    broken = artifacts() / "adr" / "broken.md"
    broken.write_text("no frontmatter\n", encoding="utf-8")

    read = adr.decisions(load(tmp_path))

    assert [d.id for d in read.decisions] == [result.entity_id]
    assert read.unreadable == (broken,)
