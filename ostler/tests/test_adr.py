"""The Decision record: ``adr.propose`` writes ``docs/adrs/<slug>/adr.md`` under the docs home and binds its evidence."""

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


def shelve(home: Path) -> tuple[Graph, list[str]]:
    core_config.ensure_artifacts_repo()
    graph = load(home)
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
    return load(home), ["acme-1", "acme-2", "acme-3"]


def propose(graph: Graph, evidence: list[str], slug: str = "guard-every-total") -> Result:
    return adr.propose(
        graph, slug=slug, title="Guard every total", context="Three records share a cause.",
        decision="Guard the total in one place.", consequences="One module owns the rule.",
        evidence=evidence,
    )


def record_text(graph: Graph, record_id: str) -> str:
    folder = register.locate(graph, record_id)
    assert folder is not None
    return (folder / register.RECORD_FILE).read_text(encoding="utf-8")


def adr_file(home: Path, slug: str = "guard-every-total") -> Path:
    return home / "docs" / "adrs" / slug / "adr.md"


def head_of_artifacts() -> str:
    done = subprocess.run(
        ["git", "-C", str(artifacts()), "rev-parse", "--verify", "-q", "HEAD"],
        capture_output=True, text=True, check=False, timeout=30,
    )
    return done.stdout.strip()


def test_three_records_yield_one_proposed_decision_with_repos_and_evidence(tmp_path: Path) -> None:
    graph, evidence = shelve(tmp_path)

    result = propose(graph, evidence)

    assert result.ok, result.message
    assert result.entity_id == "guard-every-total"
    target = adr_file(tmp_path)
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


def test_in_the_artifacts_repo_only_the_adr_is_committed(tmp_path: Path) -> None:
    graph, evidence = shelve(artifacts())
    before = int(git("rev-list", "--count", "HEAD")) if head_of_artifacts() else 0

    result = propose(graph, evidence)

    assert result.ok, result.message
    assert int(git("rev-list", "--count", "HEAD")) == before + 1
    assert git("log", "-1", "--format=%s").strip() == f"docs: propose {result.entity_id} from 3 records"
    assert git("show", "--name-only", "--format=", "HEAD").split() == [
        f"docs/adrs/{result.entity_id}/adr.md",
    ]


def test_outside_the_artifacts_repo_nothing_is_committed(tmp_path: Path) -> None:
    core_config.ensure_artifacts_repo()
    graph, evidence = shelve(tmp_path)
    head = head_of_artifacts()

    result = propose(graph, evidence)

    assert result.ok, result.message
    assert adr_file(tmp_path).is_file()
    assert head_of_artifacts() == head
    assert not (artifacts() / "docs" / "adrs").exists()


def test_a_taken_slug_is_refused_and_the_first_decision_stays(tmp_path: Path) -> None:
    graph, evidence = shelve(tmp_path)
    first = propose(graph, evidence[:1])
    assert first.ok, first.message
    graph = load(tmp_path)
    kept = adr_file(tmp_path).read_text(encoding="utf-8")
    before = {i: record_text(graph, i) for i in evidence}

    result = propose(graph, evidence[1:])

    assert not result.ok and "already exists" in result.message
    assert adr_file(tmp_path).read_text(encoding="utf-8") == kept
    assert {i: record_text(load(tmp_path), i) for i in evidence} == before


@pytest.mark.parametrize("slug", ["", "Guard Total", "../escape", "a/b", "x" * 200])
def test_a_slug_that_is_not_a_slug_is_refused(tmp_path: Path, slug: str) -> None:
    graph, evidence = shelve(tmp_path)

    result = propose(graph, evidence, slug=slug)

    assert not result.ok
    assert not (tmp_path / "docs" / "adrs").exists()


def test_no_evidence_is_refused(tmp_path: Path) -> None:
    graph, _ = shelve(tmp_path)

    result = propose(graph, [])

    assert not result.ok
    assert not (tmp_path / "docs" / "adrs").exists()


def test_an_unknown_evidence_id_is_refused_and_named_and_nothing_is_written(tmp_path: Path) -> None:
    graph, evidence = shelve(tmp_path)
    before = {i: record_text(graph, i) for i in evidence}

    result = propose(graph, [*evidence, "acme-404"])

    assert not result.ok and "acme-404" in result.message
    assert not list((tmp_path / "docs" / "adrs").glob("*/adr.md"))
    assert {i: record_text(load(tmp_path), i) for i in evidence} == before


def test_a_record_bound_to_another_decision_is_refused_and_named(tmp_path: Path) -> None:
    graph, evidence = shelve(tmp_path)
    first = propose(graph, evidence[:2], slug="first-cause")
    assert first.ok, first.message
    graph = load(tmp_path)
    before = {i: record_text(graph, i) for i in evidence}

    result = propose(graph, evidence)

    assert not result.ok and "acme-1" in result.message
    assert [p.parent.name for p in (tmp_path / "docs" / "adrs").glob("*/adr.md")] == [first.entity_id]
    assert {i: record_text(load(tmp_path), i) for i in evidence} == before


def test_the_minted_id_is_in_the_workspace_id_space(tmp_path: Path) -> None:
    graph, evidence = shelve(tmp_path)

    result = propose(graph, evidence)

    assert result.entity_id in ids.known(load(tmp_path))
    assert result.entity_id not in evidence


def test_a_failed_commit_restores_every_file_and_removes_the_adr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph, evidence = shelve(artifacts())
    before = {i: record_text(graph, i) for i in evidence}

    def broken(*_args: object, **_kwargs: object) -> bool:
        raise subprocess.CalledProcessError(1, "git")

    monkeypatch.setattr(adr, "_commit", broken)
    result = propose(graph, evidence)

    assert not result.ok
    assert {i: record_text(load(artifacts()), i) for i in evidence} == before
    assert not adr_file(artifacts()).exists()
    assert not adr_file(artifacts()).parent.exists()


def test_decisions_lists_what_parsed_and_names_what_did_not(tmp_path: Path) -> None:
    graph, evidence = shelve(tmp_path)
    result = propose(graph, evidence)
    broken = tmp_path / "docs" / "adrs" / "broken" / "adr.md"
    broken.parent.mkdir(parents=True)
    broken.write_text("no frontmatter\n", encoding="utf-8")

    read = adr.decisions(load(tmp_path))

    assert [d.id for d in read.decisions] == [result.entity_id]
    assert read.unreadable == (broken,)
