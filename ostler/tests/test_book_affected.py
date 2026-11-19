"""`ostler book affected` reads a diff and the book and names the plays the change calls for."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from book_fakes import Clearing, Haunting, Shelving, code_repo, commit_files, git, run_shelf, shelf_book, sourced_book
from ostler.book import cli
from ostler.book.affected import calls_of
from ostler.book.service import Service

FILES = {
    "svc.go": "package shelf\n\nfunc (s *Service) Get(id string) string {\n\treturn \"a\"\n}\n\nfunc (s *Server) Get(id string) string {\n\treturn \"b\"\n}\n\nfunc helper() int {\n\treturn 1\n}\n",
    "put.go": "package shelf\n\nfunc Put(id string) string {\n\treturn id\n}\n\nfunc Other() int {\n\treturn 1\n}\n",
    "remove.go": "package shelf\n\nfunc Remove(id string) string {\n\treturn id\n}\n",
    "drawer.go": "package shelf\n\nfunc Open() int {\n\treturn 1\n}\n",
    "config.go": "package shelf\n\nvar table = map[string]int{\n\t\"a\": 1,\n}\n",
    "other.go": "package shelf\n\nfunc Stray() int {\n\treturn 1\n}\n",
    "skip_test.go": "package shelf\n\nfunc TestIt() {\n\treturn\n}\n",
}


def edited(name: str, old: str, new: str) -> dict[str, str]:
    return {name: FILES[name].replace(old, new)}


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, str]:
    base = code_repo(tmp_path / "app", FILES)
    return tmp_path / "app", base


def affect(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, service: Any, repo: Path, base: str, capsys: Any) -> tuple[int, dict[str, Any], str]:
    monkeypatch.setattr(cli, "load", lambda name: service)
    monkeypatch.setattr(cli, "_package_dir", lambda args: str(tmp_path))
    out = tmp_path / "out"
    code = cli.main(["affected", "services.shelf", "--app", str(repo), "--since", base, "--out", str(out)])
    return code, json.loads((out / "shelf-affected.json").read_text()), capsys.readouterr().out


def test_a_method_of_another_type_is_not_covered_by_the_pointer_of_the_same_bare_name(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    commit_files(where, edited("svc.go", 'return "a"', 'return "z"'))
    code, found, _ = affect(monkeypatch, tmp_path, sourced_book({"PutItem": ("svc.go::Server.Get",)}), where, base, capsys)
    assert found["uncovered"] == [{"path": "svc.go", "function": "Service.Get"}]
    assert found["chains"] == []
    assert code == 1


def test_a_method_the_pointer_names_with_its_type_is_covered(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    commit_files(where, edited("svc.go", 'return "b"', 'return "z"'))
    code, found, _ = affect(monkeypatch, tmp_path, sourced_book({"PutItem": ("svc.go::Server.Get",)}), where, base, capsys)
    assert [(c["function"], c["element"]) for c in found["chains"]] == [("Server.Get", "PutItem")]
    assert (code, found["plan"], found["uncovered"]) == (0, "partial", [])


def test_a_hunk_with_no_definition_line_counts_at_the_file_and_the_plan_stays_partial(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    commit_files(where, edited("config.go", '"a": 1', '"a": 2'))
    code, found, _ = affect(monkeypatch, tmp_path, sourced_book({"PutItem": ("config.go",), "RemoveItem": ("config.go",)}), where, base, capsys)
    assert {c["element"] for c in found["chains"]} == {"PutItem", "RemoveItem"}
    assert found["fallbacks"] == []
    assert [(w["path"], w["elements"]) for w in found["widened"]] == [("config.go", ["PutItem", "RemoveItem"])]
    assert found["only"] == ["PutItem", "RemoveItem"]
    assert (code, found["plan"]) == (0, "partial")


def test_a_helper_one_element_names_widens_to_every_element_that_names_the_file(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    commit_files(where, edited("svc.go", "return 1", "return 2"))
    book = sourced_book({"PutItem": ("svc.go::helper",), "RemoveItem": ("svc.go::Server.Get",)})
    _, found, _ = affect(monkeypatch, tmp_path, book, where, base, capsys)
    assert {c["element"] for c in found["chains"]} == {"PutItem", "RemoveItem"}
    assert found["fallbacks"] == []
    assert [(w["path"], w["elements"]) for w in found["widened"]] == [("svc.go", ["PutItem", "RemoveItem"])]
    assert found["only"] == ["PutItem", "RemoveItem"]
    assert found["plan"] == "partial"


def test_a_file_level_change_in_a_file_a_record_also_names_makes_the_plan_whole_and_names_the_record(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    commit_files(where, edited("config.go", '"a": 1', '"a": 2'))
    _, found, _ = affect(monkeypatch, tmp_path, sourced_book({"PutItem": ("config.go",), "Drawer": ("config.go",)}), where, base, capsys)
    assert found["plan"] == "whole"
    assert any("record Drawer" in f["why"] for f in found["fallbacks"])
    assert [w["elements"] for w in found["widened"]] == [["Drawer", "PutItem"]]


def test_a_function_every_namer_of_the_file_names_does_not_widen(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    commit_files(where, edited("svc.go", "return 1", "return 2"))
    book = sourced_book({"PutItem": ("svc.go::helper",), "RemoveItem": ("svc.go::helper",)})
    _, found, _ = affect(monkeypatch, tmp_path, book, where, base, capsys)
    assert found["fallbacks"] == []
    assert found["plan"] == "partial"


def test_a_file_the_book_ignores_is_listed_as_ignored_and_the_plan_is_none(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    commit_files(where, edited("skip_test.go", "return", "return 1"))
    code, found, out = affect(monkeypatch, tmp_path, sourced_book({}), where, base, capsys)
    assert found["ignored"] == ["skip_test.go"]
    assert (code, found["plan"]) == (0, "none")
    assert "skip_test.go" in out
    assert out.splitlines()[-1] == "nothing to play"


def test_a_change_nobody_committed_is_seen_and_the_output_says_so(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    (where / "put.go").write_text(FILES["put.go"].replace("return id", "return id + id"))
    _, found, out = affect(monkeypatch, tmp_path, sourced_book({"PutItem": ("put.go::Put",)}), where, base, capsys)
    assert found["dirty"] is True
    assert [(c["function"], c["element"]) for c in found["chains"]] == [("Put", "PutItem")]
    assert "uncommitted" in out


def test_a_staged_change_is_seen(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    (where / "put.go").write_text(FILES["put.go"].replace("return id", "return id + id"))
    git(where, "add", "put.go")
    _, found, _ = affect(monkeypatch, tmp_path, sourced_book({"PutItem": ("put.go::Put",)}), where, base, capsys)
    assert [c["element"] for c in found["chains"]] == ["PutItem"]


def test_an_untracked_file_no_element_names_is_uncovered(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    (where / "fresh.go").write_text("package shelf\n\nfunc Fresh() int {\n\treturn 1\n}\n")
    code, found, _ = affect(monkeypatch, tmp_path, sourced_book({"PutItem": ("put.go::Put",)}), where, base, capsys)
    assert found["uncovered"] == [{"path": "fresh.go", "function": ""}]
    assert (code, found["dirty"]) == (1, True)


def test_an_untracked_file_an_element_names_counts_at_the_file(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    (where / "fresh.go").write_text("package shelf\n\nfunc Fresh() int {\n\treturn 1\n}\n")
    _, found, _ = affect(monkeypatch, tmp_path, sourced_book({"PutItem": ("fresh.go::Fresh",)}), where, base, capsys)
    assert [(c["path"], c["element"]) for c in found["chains"]] == [("fresh.go", "PutItem")]
    assert found["plan"] == "partial"
    assert [w["path"] for w in found["widened"]] == ["fresh.go"]


def test_every_changed_path_is_in_exactly_one_of_mapped_uncovered_and_ignored(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    commit_files(where, {**edited("put.go", "return id", "return id + id"), **edited("skip_test.go", "return", "return 1"),
                         **edited("svc.go", 'return "a"', 'return "z"'), **edited("other.go", "return 1", "return 2")})
    (where / "fresh.go").write_text("package shelf\n\nfunc Fresh() int {\n\treturn 1\n}\n")
    (where / "remove.go").write_text(FILES["remove.go"].replace("return id", "return id + id"))
    book = sourced_book({"PutItem": ("put.go::Put", "svc.go::Server.Get"), "RemoveItem": ("remove.go::Remove",)})
    _, found, _ = affect(monkeypatch, tmp_path, book, where, base, capsys)
    changed = set(git(where, "diff", "--name-only", base).split()) | {"fresh.go"}
    uncovered = {u["path"] for u in found["uncovered"]}
    lists = [set(found["mapped"]), uncovered, set(found["ignored"])]
    assert set().union(*lists) == changed
    assert sum(len(x) for x in lists) == len(changed)
    assert set(found["mapped"]) == {"put.go", "remove.go"}
    assert uncovered == {"svc.go", "other.go", "fresh.go"}


def test_a_changed_record_makes_the_plan_the_whole_book(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    commit_files(where, edited("drawer.go", "return 1", "return 2"))
    code, found, out = affect(monkeypatch, tmp_path, sourced_book({"Drawer": ("drawer.go::Open",)}), where, base, capsys)
    assert found["plan"] == "whole"
    assert found["fallbacks"] == [{"path": "drawer.go", "why": "record Drawer changed: the whole book"}]
    assert out.splitlines()[-1] == "ostler book run services.shelf"
    assert code == 0


def test_a_change_to_one_call_gives_a_partial_plan_and_the_command_to_run(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    commit_files(where, edited("remove.go", "return id", "return id + id"))
    code, found, out = affect(monkeypatch, tmp_path, sourced_book({"RemoveItem": ("remove.go::Remove",)}), where, base, capsys)
    assert (code, found["plan"], found["only"], found["journeys"]) == (0, "partial", ["RemoveItem"], ["Clearing"])
    assert "  remove.go::Remove -> RemoveItem (endpoint) -> RemoveItem, Clearing" in out.splitlines()
    assert out.splitlines()[-1] == "ostler book run services.shelf --only RemoveItem"


def test_no_change_gives_the_plan_none(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    code, found, out = affect(monkeypatch, tmp_path, sourced_book({"PutItem": ("put.go::Put",)}), where, base, capsys)
    assert (code, found["plan"], found["dirty"], found["only"]) == (0, "none", False, [])
    assert out.splitlines()[-1] == "nothing to play"


def test_an_action_reaches_every_call_and_outside_happening_that_carries_it(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    commit_files(where, edited("put.go", "return id", "return id + id"))
    code, found, _ = affect(monkeypatch, tmp_path, sourced_book({"Put": ("put.go::Put",)}), where, base, capsys)
    assert [(c["element"], c["kind"]) for c in found["chains"]] == [("Put", "action")]
    assert found["chains"][0]["plays"] == ["Arrives", "PutItem", "Shelving", "Clearing"]
    assert (code, found["plan"], found["only"]) == (0, "partial", ["Arrives", "PutItem"])
    assert found["journeys"] == ["Shelving", "Clearing"]


def test_an_outside_happening_gives_itself_and_the_journeys_that_arrange_it(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    commit_files(where, edited("put.go", "return id", "return id + id"))
    _, found, _ = affect(monkeypatch, tmp_path, sourced_book({"Arrives": ("put.go::Put",)}), where, base, capsys)
    assert [(c["element"], c["kind"], c["plays"]) for c in found["chains"]] == [("Arrives", "outside", ["Arrives", "Shelving"])]


def test_the_report_holds_the_fields_the_caller_reads_and_what_it_did_not_walk(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    head = commit_files(where, edited("remove.go", "return id", "return id + id"))
    _, found, out = affect(monkeypatch, tmp_path, sourced_book({"RemoveItem": ("remove.go::Remove",)}), where, base, capsys)
    assert set(found) == {"service", "base", "head", "dirty", "plan", "only", "journeys", "chains", "uncovered", "ignored", "fallbacks", "widened",
                          "not_computed", "mapped"}
    assert (found["service"], found["base"], found["head"]) == ("shelf", base, head)
    assert set(found["chains"][0]) == {"path", "function", "element", "kind", "plays"}
    assert [n.split(":")[0] for n in found["not_computed"]] == ["dependent books", "configuration", "data", "code in other repositories"]
    assert f"written: {tmp_path / 'out' / 'shelf-affected.json'}" in out


def test_an_uncovered_function_exits_1_and_the_plan_is_still_written(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    commit_files(where, {**edited("remove.go", "return id", "return id + id"), **edited("put.go", "return 1", "return 2")})
    code, found, out = affect(monkeypatch, tmp_path, sourced_book({"RemoveItem": ("remove.go::Remove", "put.go::Put")}), where, base, capsys)
    assert found["uncovered"] == [{"path": "put.go", "function": "Other"}]
    assert (code, found["plan"], found["only"]) == (1, "partial", ["RemoveItem"])
    assert "put.go::Other" in out
    assert out.splitlines()[-1] == "ostler book run services.shelf --only RemoveItem"


def test_a_book_with_no_commit_to_judge_against_says_so(monkeypatch, tmp_path, capsys, repo):
    where, _ = repo
    monkeypatch.setattr(cli, "load", lambda name: sourced_book({}))
    monkeypatch.setattr(cli, "_package_dir", lambda args: str(tmp_path))
    assert cli.main(["affected", "services.shelf", "--app", str(where), "--out", str(tmp_path / "out")]) == 2
    assert "not verified" in capsys.readouterr().out


def test_with_no_out_the_report_goes_to_a_temp_folder_the_output_names(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    monkeypatch.setattr(cli, "load", lambda name: sourced_book({}))
    monkeypatch.setattr(cli, "_package_dir", lambda args: str(tmp_path))
    assert cli.main(["affected", "services.shelf", "--app", str(where), "--since", base]) == 0
    folder = capsys.readouterr().out.rsplit("reports: ", 1)[1].strip()
    assert Path(folder, "shelf-affected.json").exists()


def test_a_screen_reaches_its_interactions_and_a_record_no_call():
    screen = type("Dashboard", (), {})
    service = cast("Service[Any]", SimpleNamespace(interactions=(SimpleNamespace(__name__="Tap", screen=screen),
                                                                  SimpleNamespace(__name__="Idle", screen=None))))
    assert calls_of(service, screen, "screen") == {"Tap"}
    assert calls_of(service, screen, "record") is None


def test_run_only_accepts_an_outside_happening_and_keeps_the_journeys_that_arrange_it(monkeypatch, tmp_path, capsys):
    code, out = run_shelf(monkeypatch, shelf_book(journeys=(Haunting, Shelving, Clearing)), tmp_path, capsys, "--only", "Ghost")
    assert "only what calls Ghost: 1 of 3 journeys" in out
    assert "Haunting" in out
    assert "Shelving" not in out


def test_run_only_still_refuses_a_name_the_book_does_not_have(monkeypatch, tmp_path, capsys):
    with pytest.raises(SystemExit, match="--only names no endpoint or interaction or outside happening of shelf: Nobody"):
        run_shelf(monkeypatch, shelf_book(), tmp_path, capsys, "--only", "Nobody")
