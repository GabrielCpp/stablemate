from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from ostler import Ostler, crud
from ostler.cli import main
from ostler.model import load
from ostler.provenance import commit_story, node_provenance, story_provenance

def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _commit(root: Path, message: str) -> str:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def _fixture(tmp_path: Path) -> tuple[Path, Path, str, str]:
    docs = tmp_path / "product-docs"
    source = tmp_path / "api-service"
    docs.mkdir()
    source.mkdir()
    created_epic = crud.create_epic(load(docs), "billing", "Billing", prefix="BILL")
    assert created_epic.ok
    created_story = crud.create_story(load(docs), "billing", "create-invoice", "Create invoice")
    assert created_story.ok
    story = load(docs).find_story("create-invoice")
    assert story is not None
    story_id = story[1].eid
    feature = docs / "docs/features/billing/create.md"
    feature.parent.mkdir(parents=True)
    feature.write_text(
        "---\ntype: concept\nslug: create\ntitle: Create invoice\n---\n"
        "# Create invoice\n\n- code: `repo://api-service/src/service.py::create_invoice`\n",
        encoding="utf-8",
    )

    _git(source, "init", "-q", "-b", "main")
    _git(source, "config", "user.email", "test@example.com")
    _git(source, "config", "user.name", "Test")
    implementation = source / "src/service.py"
    implementation.parent.mkdir(parents=True)
    implementation.write_text("def create_invoice():\n    return 0\n", encoding="utf-8")
    base = _commit(source, "seed")
    implementation.write_text("def create_invoice():\n    return 1\n", encoding="utf-8")
    _commit(source, "feat: create invoice\n\nStory: create-invoice")
    implementation.write_text("def create_invoice():\n    return 2\n", encoding="utf-8")
    _commit(source, f"fix: invoice result\n\nStory: {story_id}")
    implementation.write_text("def create_invoice():\n    return 3\n", encoding="utf-8")
    _commit(source, f"chore: unrelated trailer\n\nStory: {story_id}-extra")

    graph = load(docs)
    node = graph.find_ui_node("docs/features/billing/create.md")
    assert node is not None
    packet = {
        "version": 2,
        "story": {"id": story_id, "slug": "create-invoice"},
        "repositories": [{"id": "api-service", "baseSha": base}],
        "changedUnits": [
            {
                "id": "repo://api-service/src/service.py",
                "repository": "api-service",
                "path": "src/service.py",
            }
        ],
        "directNodes": [
            {
                "node": node.id,
                "reasons": [
                    {
                        "kind": "changed-code",
                        "ref": "repo://api-service/src/service.py::create_invoice",
                    }
                ],
            }
        ],
        "contracts": [node.id],
        "journeys": [],
    }
    spec = docs / Ostler(docs).spec_path(story_id)
    spec.mkdir(parents=True, exist_ok=True)
    (spec / "qa-okf-context.json").write_text(
        json.dumps(packet, indent=2), encoding="utf-8"
    )
    return docs, source, story_id, node.id


def test_story_provenance_joins_exact_commits_to_the_context_packet(
    tmp_path: Path,
) -> None:
    docs, source, story_id, node_id = _fixture(tmp_path)

    result = Ostler(docs).query(
        "story-provenance",
        "create-invoice",
        checkouts={"api-service": source},
    )[0]

    assert result["story"]["id"] == story_id
    assert [row["storyTrailers"] for row in result["commits"]] == [
        ["create-invoice"],
        [story_id],
    ]
    assert result["changedUnits"][0]["repository"] == "api-service"
    assert result["directNodes"][0]["node"] == node_id
    assert result["warnings"] == []


def test_commit_story_returns_resolved_and_unresolved_exact_trailers(
    tmp_path: Path,
) -> None:
    docs, source, story_id, _node_id = _fixture(tmp_path)
    marker = source / "marker.txt"
    marker.write_text("both\n", encoding="utf-8")
    sha = _commit(
        source,
        f"feat: shared change\n\nStory: {story_id}\nStory: TRACKER-404",
    )

    result = commit_story(load(docs), f"api-service@{sha[:8]}", {"api-service": source})[0]

    assert result["sha"] == sha
    assert result["stories"][0]["resolved"] is True
    assert result["stories"][0]["id"] == story_id
    assert result["stories"][1] == {"trailer": "TRACKER-404", "resolved": False}


def test_node_provenance_reads_reverse_story_roles_and_commits(tmp_path: Path) -> None:
    docs, source, story_id, node_id = _fixture(tmp_path)

    result = node_provenance(
        load(docs), node_id, {"api-service": source}
    )[0]

    assert result["node"]["codeRefs"] == [
        "repo://api-service/src/service.py::create_invoice"
    ]
    assert result["stories"][0]["story"]["id"] == story_id
    assert result["stories"][0]["roles"] == ["direct", "contract"]
    assert len(result["stories"][0]["commits"]) == 2


def test_node_provenance_survives_a_node_removed_from_the_current_graph(
    tmp_path: Path,
) -> None:
    docs, source, story_id, node_id = _fixture(tmp_path)
    (docs / "docs/features/billing/create.md").unlink()

    result = node_provenance(
        load(docs), node_id, {"api-service": source}
    )[0]

    assert result["node"] == {"id": node_id}
    assert result["stories"][0]["story"]["id"] == story_id
    assert result["stories"][0]["roles"] == ["direct", "contract"]


def test_story_provenance_reports_missing_checkout_and_packet(tmp_path: Path) -> None:
    docs, _source, story_id, _node_id = _fixture(tmp_path)
    spec = docs / Ostler(docs).spec_path(story_id)
    (spec / "qa-okf-context.json").unlink()

    result = story_provenance(load(docs), story_id, {})[0]

    assert result["commits"] == []
    assert "has no generated context packet" in result["warnings"][0]


def test_story_provenance_reports_a_missing_required_checkout(tmp_path: Path) -> None:
    docs, _source, story_id, _node_id = _fixture(tmp_path)

    result = story_provenance(load(docs), story_id, {})[0]

    assert result["commits"] == []
    assert result["warnings"] == [
        "no checkout supplied for repository 'api-service'"
    ]


def test_story_provenance_reads_legacy_changed_code(tmp_path: Path) -> None:
    docs, _source, story_id, _node_id = _fixture(tmp_path)
    spec = docs / Ostler(docs).spec_path(story_id)
    (spec / "qa-okf-context.json").write_text(
        json.dumps({"version": 1, "changedCode": [{"path": "service.py"}]}),
        encoding="utf-8",
    )

    result = story_provenance(load(docs), story_id, {})[0]

    assert result["changedUnits"] == [{"path": "service.py"}]


def test_cli_emits_story_provenance_with_checkout_mapping(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    docs, source, story_id, _node_id = _fixture(tmp_path)

    status = main(
        [
            "-C",
            str(docs),
            "query",
            "story-provenance",
            story_id,
            "--checkout",
            f"api-service={source}",
            "--json",
        ]
    )

    assert status == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["story"]["id"] == story_id
    assert len(payload[0]["commits"]) == 2
