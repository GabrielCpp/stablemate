"""Short handles end to end: the universe they abbreviate within, the render seam, the CLI modes."""

from __future__ import annotations

import json
from pathlib import Path

from ostler import crud, ids
from ostler.api import Ostler
from ostler.cli import main
from ostler.model import load


def run(root: Path, *argv: str) -> int:
    return main(["-C", str(root), *argv])


def _repo(tmp_path: Path) -> tuple[Ostler, dict[str, str]]:
    """A repo carrying one of each id-bearing thing, and the ids it minted."""
    (tmp_path / ".git").mkdir(parents=True, exist_ok=True)
    okf = Ostler(tmp_path)
    epic = okf.create_epic("checkout", "Checkout").entity_id
    seed = okf.allocate_id()
    okf.add_seed("checkout", seed, status="researched", summary="take a payment")
    story = okf.create_story("checkout", "01-pay", "Pay", covers=[seed]).entity_id
    feature = okf._apply(crud.create_feature(okf._fresh(), "basket", "Basket")).entity_id
    item = okf.allocate_id()
    okf.backlog_add(item, "wire the receipt email")
    return okf, {"epic": epic, "seed": seed, "story": story,
                 "feature": feature, "backlog": item}



def test_known_collects_ids_from_every_place_they_are_written(tmp_path: Path):
    okf, minted = _repo(tmp_path)
    known = ids.known(okf.reload().graph)
    for kind, identifier in minted.items():
        assert identifier in known, kind
    assert known == sorted(known)


def test_known_is_the_same_set_for_every_command(tmp_path: Path):
    okf, _ = _repo(tmp_path)
    graph = okf.reload().graph
    assert ids.known(graph) == ids.known(okf.reload().graph)



def test_table_agrees_with_abbreviate_for_every_id(tmp_path: Path):
    okf, _ = _repo(tmp_path)
    known = ids.known(okf.graph)
    assert ids.table(known) == {i: ids.abbreviate(i, known) for i in known}


def test_table_leaves_a_legacy_id_whole(tmp_path: Path):
    assert ids.table(["ACME-42", "ACME-" + "0" * 26])["ACME-42"] == "ACME-42"



def test_shorten_rewrites_ids_inside_strings_lists_and_values(tmp_path: Path):
    okf, minted = _repo(tmp_path)
    table = ids.table(ids.known(okf.graph))
    epic = minted["epic"]
    row = {"id": epic, "covers": [minted["seed"]], "text": f"see {epic} for context"}
    out = ids.shorten(row, table)
    assert out["id"] == table[epic]
    assert out["covers"] == [table[minted["seed"]]]
    assert out["text"] == f"see {table[epic]} for context"


def test_shorten_leaves_keys_alone(tmp_path: Path):
    okf, minted = _repo(tmp_path)
    table = ids.table(ids.known(okf.graph))
    assert list(ids.shorten({minted["epic"]: "frozen"}, table)) == [minted["epic"]]


def test_shorten_does_not_touch_things_that_merely_look_id_ish():
    table = {"ACME-" + "0" * 26: "ACME-KKKKKK"}
    for text in ("docs/epics/0001-checkout/stories/01-pay/story.md",
                 "docs/features/area/rec.md#the-anchor",
                 "a hyphenated-word in prose",
                 "ACME-" + "0" * 25):
        assert ids.shorten(text, table) == text



def test_resolve_expands_a_handle_and_passes_anything_else_through(tmp_path: Path):
    okf, minted = _repo(tmp_path)
    graph = okf.graph
    handle = ids.table(ids.known(graph))[minted["seed"]]
    assert ids.resolve(graph, handle) == minted["seed"]
    assert ids.resolve(graph, minted["seed"]) == minted["seed"]
    assert ids.resolve(graph, "01-pay") == "01-pay"
    assert ids.resolve(graph, "") == ""



def test_human_output_abbreviates_and_json_does_not(tmp_path: Path, capsys):
    okf, minted = _repo(tmp_path)
    handle = ids.table(ids.known(okf.graph))[minted["epic"]]

    assert run(tmp_path, "list", "--type", "epic") == 0
    human = capsys.readouterr().out
    assert handle in human and minted["epic"] not in human

    assert run(tmp_path, "list", "--type", "epic", "--json") == 0
    rows = json.loads(capsys.readouterr().out)
    assert any(r.get("id") == minted["epic"] for r in rows)


def test_the_flags_override_either_default(tmp_path: Path, capsys):
    okf, minted = _repo(tmp_path)
    handle = ids.table(ids.known(okf.graph))[minted["epic"]]

    assert run(tmp_path, "--full-ids", "list", "--type", "epic") == 0
    assert minted["epic"] in capsys.readouterr().out

    assert run(tmp_path, "--handles", "list", "--type", "epic", "--json") == 0
    assert handle in capsys.readouterr().out


def test_a_freshly_minted_id_prints_as_a_handle(tmp_path: Path, capsys):
    (tmp_path / ".git").mkdir()
    capsys.readouterr()
    assert run(tmp_path, "create", "epic", "checkout", "--title", "Checkout") == 0
    printed = capsys.readouterr().out
    minted = Ostler(tmp_path).graph.epics[0].eid
    assert minted not in printed
    assert ids.abbreviate(minted, [minted]) in printed



def test_a_handle_is_accepted_wherever_an_id_is(tmp_path: Path, capsys):
    okf, minted = _repo(tmp_path)
    table = ids.table(ids.known(okf.graph))

    assert run(tmp_path, "query", "stories-covering-seed",
               table[minted["seed"]], "--json") == 0
    assert json.loads(capsys.readouterr().out), "the handle resolved to the seed"

    assert run(tmp_path, "backlog", "prune", table[minted["backlog"]]) == 0
    assert minted["backlog"] not in (tmp_path / "docs/backlog.md").read_text()


def test_seed_add_by_handle_updates_rather_than_filing_a_second_seed(tmp_path: Path):
    okf, minted = _repo(tmp_path)
    handle = ids.table(ids.known(okf.graph))[minted["seed"]]
    assert run(tmp_path, "seed", "add", "checkout", handle,
               "--status", "resolved", "--summary", "done") == 0
    seeds = load(tmp_path).epics[0].seeds
    assert [s.id for s in seeds] == [minted["seed"]]
    assert seeds[0].status == "resolved"
