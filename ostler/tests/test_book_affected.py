"""`ostler book affected` reads a diff and the book and names the plays the change calls for."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from book_fakes import Clearing, Haunting, Shelving, affected_report, app_repo, code_repo, commit_files, git, run_shelf, shelf_book, sourced_book
from ostler.book import cli
from ostler.book import affected as affected_module
from ostler.book.affected import calls_of
from ostler.book.screen import Screen
from ostler.book.service import Service
from ostler.book.sources import defined

FILES = {
    "svc.go": "package shelf\n\nfunc (s *Service) Get(id string) string {\n\treturn \"a\"\n}\n\nfunc (s *Server) Get(id string) string {\n\treturn \"b\"\n}\n\nfunc helper() int {\n\treturn 1\n}\n",
    "put.go": "package shelf\n\nfunc Put(id string) string {\n\treturn id\n}\n\nfunc Other() int {\n\treturn 1\n}\n",
    "remove.go": "package shelf\n\nfunc Remove(id string) string {\n\treturn id\n}\n",
    "drawer.go": "package shelf\n\nfunc Open() int {\n\treturn 1\n}\n",
    "config.go": "package shelf\n\n// sizes: a\n",
    "other.go": "package shelf\n\nfunc Stray() int {\n\treturn 1\n}\n",
    "box.go": "package shelf\n\ntype Box struct {\n\tName string\n\tSize int\n}\n\nfunc Fill() int {\n\treturn 1\n}\n\nfunc Empty() int {\n\treturn 2\n}\n",
    "mixed.go": "package shelf\n\n// sizes: a\n\nfunc Fill() int {\n\treturn 1\n}\n",
    "twice.go": "package shelf\n\n// one\n\n// two\n",
    "skip_test.go": "package shelf\n\nfunc TestIt() {\n\treturn\n}\n",
}


def edited(name: str, old: str, new: str) -> dict[str, str]:
    return {name: FILES[name].replace(old, new)}


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, str]:
    return app_repo(tmp_path, FILES)


def affect(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, service: Any, repo: Path, base: str, capsys: Any) -> tuple[int, dict[str, Any], str]:
    return affected_report(monkeypatch, tmp_path, service, capsys, "--app", str(repo), "--since", base)


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
    commit_files(where, edited("config.go", "sizes: a", "sizes: b"))
    code, found, _ = affect(monkeypatch, tmp_path, sourced_book({"PutItem": ("config.go",), "RemoveItem": ("config.go",)}), where, base, capsys)
    assert {c["element"] for c in found["chains"]} == {"PutItem", "RemoveItem"}
    assert found["fallbacks"] == []
    assert [(w["path"], w["elements"]) for w in found["widened"]] == [("config.go", ["PutItem", "RemoveItem"])]
    assert found["only"] == ["PutItem", "RemoveItem"]
    assert (code, found["plan"]) == (0, "partial")


def test_a_helper_one_element_names_does_not_widen_to_the_other_elements_of_the_file(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    commit_files(where, edited("svc.go", "return 1", "return 2"))
    book = sourced_book({"PutItem": ("svc.go::helper",), "RemoveItem": ("svc.go::Server.Get",)})
    _, found, _ = affect(monkeypatch, tmp_path, book, where, base, capsys)
    assert [(c["element"], c["via"]) for c in found["chains"]] == [("PutItem", "direct")]
    assert (found["fallbacks"], found["widened"], found["only"], found["plan"]) == ([], [], ["PutItem"], "partial")


def test_a_file_level_change_in_a_file_a_record_also_names_makes_the_plan_whole_and_names_the_record(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    commit_files(where, edited("config.go", "sizes: a", "sizes: b"))
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


def test_a_struct_change_hits_the_record_that_points_at_it_and_makes_the_plan_whole(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    commit_files(where, edited("box.go", "Size int", "Size int64"))
    _, found, _ = affect(monkeypatch, tmp_path, sourced_book({"Drawer": ("box.go::Box",), "PutItem": ("box.go::Fill",)}), where, base, capsys)
    assert found["plan"] == "whole"
    assert found["fallbacks"] == [{"path": "box.go", "why": "record Drawer changed: the whole book"}]
    assert [(c["function"], c["element"]) for c in found["chains"]] == [("Box", "Drawer")]


def test_a_change_to_another_function_in_a_record_s_file_leaves_the_record_out(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    commit_files(where, edited("box.go", "func Fill() int {\n\treturn 1", "func Fill() int {\n\treturn 3"))
    _, found, _ = affect(monkeypatch, tmp_path, sourced_book({"Drawer": ("box.go::Box",), "PutItem": ("box.go::Fill",)}), where, base, capsys)
    assert [(c["function"], c["element"]) for c in found["chains"]] == [("Fill", "PutItem")]
    assert (found["plan"], found["fallbacks"], found["widened"], found["only"]) == ("partial", [], [], ["PutItem"])


def test_a_record_that_points_at_the_file_with_no_symbol_is_touched_by_any_change_to_it(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    commit_files(where, edited("box.go", "func Fill() int {\n\treturn 1", "func Fill() int {\n\treturn 3"))
    _, found, _ = affect(monkeypatch, tmp_path, sourced_book({"Drawer": ("box.go",), "PutItem": ("box.go::Fill",)}), where, base, capsys)
    assert found["plan"] == "whole"


def test_an_unattributed_hunk_does_not_hide_the_function_next_to_it(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    commit_files(where, {"mixed.go": FILES["mixed.go"].replace("sizes: a", "sizes: b").replace("return 1", "return 3")})
    book = sourced_book({"PutItem": ("mixed.go::Fill",), "RemoveItem": ("mixed.go::Remove",)})
    _, found, _ = affect(monkeypatch, tmp_path, book, where, base, capsys)
    assert [(c["function"], c["element"]) for c in found["chains"]] == [("Fill", "PutItem"), ("", "PutItem"), ("", "RemoveItem")]
    assert [w["elements"] for w in found["widened"]] == [["PutItem", "RemoveItem"]]
    assert "no definition line" in found["widened"][0]["why"]
    assert (found["plan"], found["only"], found["uncovered"]) == ("partial", ["PutItem", "RemoveItem"], [])


def test_an_unattributed_hunk_in_a_file_a_record_names_makes_the_plan_whole(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    commit_files(where, edited("mixed.go", "sizes: a", "sizes: b"))
    _, found, _ = affect(monkeypatch, tmp_path, sourced_book({"Drawer": ("mixed.go::Fill",), "PutItem": ("mixed.go::Fill",)}), where, base, capsys)
    assert found["plan"] == "whole"
    assert [f["why"] for f in found["fallbacks"]] == ["record Drawer names the file and a changed hunk has no definition line: the whole book"]


def test_a_changed_function_does_not_reach_the_other_elements_of_its_file(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    commit_files(where, edited("box.go", "func Fill() int {\n\treturn 1", "func Fill() int {\n\treturn 3"))
    book = sourced_book({"PutItem": ("box.go::Fill",), "RemoveItem": ("box.go::Empty",), "Drawer": ("box.go::Box",)})
    _, found, _ = affect(monkeypatch, tmp_path, book, where, base, capsys)
    assert {c["element"] for c in found["chains"]} == {"PutItem"}
    assert (found["plan"], found["fallbacks"], found["widened"]) == ("partial", [], [])


def test_the_same_fallback_and_widening_are_listed_once_per_path_and_reason(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    commit_files(where, {"twice.go": FILES["twice.go"].replace("one", "uno").replace("two", "dos")})
    book = sourced_book({"Drawer": ("twice.go",), "PutItem": ("twice.go",)})
    _, found, out = affect(monkeypatch, tmp_path, book, where, base, capsys)
    assert len(found["fallbacks"]) == 1
    assert len(found["widened"]) == 1
    assert sum(line.startswith("  twice.go: record Drawer") for line in out.splitlines()) == 1


def test_two_changed_functions_of_one_record_list_its_fallback_once(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    commit_files(where, {"box.go": FILES["box.go"].replace("return 1", "return 3").replace("return 2", "return 4")})
    _, found, _ = affect(monkeypatch, tmp_path, sourced_book({"Drawer": ("box.go",)}), where, base, capsys)
    assert found["fallbacks"] == [{"path": "box.go", "why": "record Drawer changed: the whole book"}]


@pytest.mark.parametrize("line, name", [
    ("type Ticket struct {", "Ticket"),
    ("type Store interface {", "Store"),
    ("type Handler func(w int)", "Handler"),
    ("class Ticket(Base):", "Ticket"),
    ("export class Ticket extends Base {", "Ticket"),
    ("export interface Ticket {", "Ticket"),
    ("export type Ticket = {", "Ticket"),
    ("export const enum Level {", "Level"),
    ("const Limit = 5", "Limit"),
    ("var table = map[string]int{", "table"),
    ("LIMIT = 5", "LIMIT"),
    ("LIMIT: int = 5", "LIMIT"),
    ("export const LIMIT = 5;", "LIMIT"),
    ("const limit = 5", "limit"),
    ("let count = 0;", "count"),
    ("var legacy = 1;", "legacy"),
])
def test_a_type_declaration_or_package_level_value_is_a_definition_when_asked(line, name):
    assert defined(line, types=True) == name
    assert defined(line) is None


@pytest.mark.parametrize("line", ["\tx = 5", "    const inner = 3", "if x == 5:", "const (", "var (", "x += 1"])
def test_a_local_assignment_or_block_opener_is_no_definition(line):
    assert defined(line, types=True) is None


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
    assert "  remove.go::Remove -> RemoveItem (endpoint, direct) -> RemoveItem, Clearing" in out.splitlines()
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
    assert set(found) == {"service", "base", "head", "dirty", "plan", "whole", "reason", "only", "journeys", "by_journey", "diff", "chains", "uncovered",
                          "unplayed", "ignored", "fallbacks", "widened", "not_computed", "mapped", "imports", "unused", "story", "commits", "owed"}
    assert (found["service"], found["base"], found["head"]) == ("shelf", base, head)
    assert set(found["chains"][0]) == {"path", "function", "element", "kind", "plays", "via"}
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


HANDLERS = ("package shelf\n\nfunc Put(id string) string {\n\treturn help(id)\n}\n\nfunc Remove(id string) string {\n\treturn help(id) + \"x\"\n}\n\n"
            "func help(id string) string {\n\treturn id\n}\n\nfunc Other(id string) string {\n\treturn id\n}\n")
LIMITS = ("package shelf\n\nconst (\n\tLimit = 5\n\tFloor = 1\n)\n\nfunc help(id string) int {\n\treturn len(id) + Limit\n}\n\n"
          "func Put(id string) int {\n\treturn help(id)\n}\n\nfunc Remove(id string) int {\n\treturn Floor\n}\n")
IMPORTS = "package shelf\n\nimport (\n\t\"fmt\"\n)\n\nfunc Put(id string) string {\n\treturn fmt.Sprint(id)\n}\n"
RENDER = "package shelf\n\nfunc Render() string {\n\treturn \"a\"\n}\n"
CALLER = "package shelf\n\nfunc {name}() string {{\n\treturn Render()\n}}\n"
BROKEN = ("package shelf\n\nfunc Put() string {\n\treturn \"p\"\n}\n\nfunc help() string {\n\treturn \"a\"\n}\n\n"
          "func broken() string {\n\treturn \"b\"\n")


def scene(tmp_path: Path, files: dict[str, str]) -> tuple[Path, str]:
    return tmp_path / "app", code_repo(tmp_path / "app", files)


def vias(found: dict[str, Any]) -> list[tuple[str, str, str]]:
    return [(c["function"], c["element"], c["via"]) for c in found["chains"]]


def test_a_helper_two_handlers_use_reaches_the_element_that_names_the_handler(monkeypatch, tmp_path, capsys):
    where, base = scene(tmp_path, {"h.go": HANDLERS})
    commit_files(where, {"h.go": HANDLERS.replace("func help(id string) string {\n\treturn id", "func help(id string) string {\n\treturn id + \"!\"")})
    book = sourced_book({"PutItem": ("h.go::help",), "RemoveItem": ("h.go::Remove",), "RestockItem": ("h.go::Other",)})
    _, found, _ = affect(monkeypatch, tmp_path, book, where, base, capsys)
    assert vias(found) == [("help", "PutItem", "direct"), ("help", "RemoveItem", "through help")]
    assert (found["only"], found["widened"], found["fallbacks"], found["plan"]) == (["PutItem", "RemoveItem"], [], [], "partial")


def test_a_handler_no_other_handler_mentions_reaches_only_its_own_element(monkeypatch, tmp_path, capsys):
    where, base = scene(tmp_path, {"h.go": HANDLERS})
    commit_files(where, {"h.go": HANDLERS.replace("func Other(id string) string {\n\treturn id", "func Other(id string) string {\n\treturn id + \"!\"")})
    book = sourced_book({"PutItem": ("h.go::Put",), "RemoveItem": ("h.go::Remove",), "RestockItem": ("h.go::Other",)})
    _, found, _ = affect(monkeypatch, tmp_path, book, where, base, capsys)
    assert vias(found) == [("Other", "RestockItem", "direct")]
    assert found["only"] == ["RestockItem"]


def test_a_changed_constant_reaches_the_elements_whose_functions_mention_it(monkeypatch, tmp_path, capsys):
    where, base = scene(tmp_path, {"c.go": LIMITS})
    commit_files(where, {"c.go": LIMITS.replace("Limit = 5", "Limit = 6")})
    book = sourced_book({"PutItem": ("c.go::Put",), "RemoveItem": ("c.go::Remove",)})
    _, found, out = affect(monkeypatch, tmp_path, book, where, base, capsys)
    assert vias(found) == [("Limit", "PutItem", "through help")]
    assert (found["widened"], found["fallbacks"], found["uncovered"], found["plan"]) == ([], [], [], "partial")
    assert any(line.startswith("  c.go::Limit -> PutItem (endpoint, through help) -> ") for line in out.splitlines())


def test_a_constant_the_element_names_is_direct(monkeypatch, tmp_path, capsys):
    where, base = scene(tmp_path, {"c.go": LIMITS})
    commit_files(where, {"c.go": LIMITS.replace("Floor = 1", "Floor = 2")})
    book = sourced_book({"PutItem": ("c.go::Put",), "RemoveItem": ("c.go::Floor",)})
    _, found, _ = affect(monkeypatch, tmp_path, book, where, base, capsys)
    assert vias(found) == [("Floor", "RemoveItem", "direct")]


def test_a_go_import_only_hunk_is_listed_under_imports_and_widens_nothing(monkeypatch, tmp_path, capsys):
    where, base = scene(tmp_path, {"i.go": IMPORTS})
    commit_files(where, {"i.go": IMPORTS.replace('\t"fmt"\n', '\t"fmt"\n\t"strings"\n')})
    code, found, out = affect(monkeypatch, tmp_path, sourced_book({"PutItem": ("i.go::Put",)}), where, base, capsys)
    assert found["imports"] == ["i.go"]
    assert (found["chains"], found["widened"], found["fallbacks"], found["uncovered"]) == ([], [], [], [])
    assert (code, found["plan"], found["mapped"]) == (0, "none", ["i.go"])
    assert "imports" in out


def test_a_blank_import_stays_unplaceable_and_counts_at_the_file(monkeypatch, tmp_path, capsys):
    where, base = scene(tmp_path, {"i.go": IMPORTS})
    commit_files(where, {"i.go": IMPORTS.replace('\t"fmt"\n', '\t"fmt"\n\t_ "embed"\n')})
    _, found, _ = affect(monkeypatch, tmp_path, sourced_book({"PutItem": ("i.go::Put",)}), where, base, capsys)
    assert found["imports"] == []
    assert vias(found) == [("", "PutItem", "direct")]
    assert [w["path"] for w in found["widened"]] == ["i.go"]


def test_a_single_line_go_import_is_an_import_hunk(monkeypatch, tmp_path, capsys):
    one = "package shelf\n\nimport \"fmt\"\n\nfunc Put(id string) string {\n\treturn fmt.Sprint(id)\n}\n"
    where, base = scene(tmp_path, {"i.go": one})
    commit_files(where, {"i.go": one.replace('import "fmt"', 'import str "fmt"')})
    _, found, _ = affect(monkeypatch, tmp_path, sourced_book({"PutItem": ("i.go::Put",)}), where, base, capsys)
    assert (found["imports"], found["chains"]) == (["i.go"], [])


def test_a_same_name_collision_is_followed_on_both(monkeypatch, tmp_path, capsys):
    files = {"a.go": RENDER, "b.go": RENDER.replace('"a"', '"b"'), "p.go": CALLER.format(name="Put"), "r.go": CALLER.format(name="Remove")}
    where, base = scene(tmp_path, files)
    commit_files(where, {"a.go": RENDER.replace('"a"', '"z"')})
    book = sourced_book({"PutItem": ("p.go::Put",), "RemoveItem": ("r.go::Remove",)})
    _, found, _ = affect(monkeypatch, tmp_path, book, where, base, capsys)
    assert vias(found) == [("Render", "PutItem", "through Render"), ("Render", "RemoveItem", "through Render")]


def test_a_file_whose_extents_cannot_be_read_is_one_unit(monkeypatch, tmp_path, capsys):
    where, base = scene(tmp_path, {"u.go": BROKEN})
    commit_files(where, {"u.go": BROKEN.replace('return "a"', 'return "z"')})
    _, found, _ = affect(monkeypatch, tmp_path, sourced_book({"PutItem": ("u.go::Put",)}), where, base, capsys)
    assert vias(found) == [("help", "PutItem", "through help")]


def test_the_same_file_closed_properly_keeps_the_extents_apart(monkeypatch, tmp_path, capsys):
    closed = BROKEN + "}\n"
    where, base = scene(tmp_path, {"u.go": closed})
    commit_files(where, {"u.go": closed.replace('return "a"', 'return "z"')})
    code, found, _ = affect(monkeypatch, tmp_path, sourced_book({"PutItem": ("u.go::Put",)}), where, base, capsys)
    assert (found["chains"], found["uncovered"], code) == ([], [{"path": "u.go", "function": "help"}], 1)


def test_a_record_whose_type_mentions_the_changed_symbol_is_touched_and_leaves_the_plan_partial(monkeypatch, tmp_path, capsys):
    text = "package shelf\n\ntype Level int\n\nfunc Hold() int {\n\treturn Level(2)\n}\n\nfunc Put() int {\n\treturn Level(1)\n}\n"
    where, base = scene(tmp_path, {"r.go": text})
    commit_files(where, {"r.go": text.replace("type Level int", "type Level int64")})
    _, found, out = affect(monkeypatch, tmp_path, sourced_book({"Drawer": ("r.go::Hold",), "PutItem": ("r.go::Put",)}), where, base, capsys)
    assert vias(found) == [("Level", "PutItem", "through Level"), ("Level", "Drawer", "through Level")]
    assert (found["plan"], found["fallbacks"], found["only"]) == ("partial", [], ["PutItem"])


def test_a_changed_symbol_that_is_the_records_own_makes_the_plan_whole(monkeypatch, tmp_path, capsys):
    text = "package shelf\n\ntype Level int\n\nfunc Put() int {\n\treturn 1\n}\n"
    where, base = scene(tmp_path, {"r.go": text})
    commit_files(where, {"r.go": text.replace("type Level int", "type Level int64")})
    _, found, _ = affect(monkeypatch, tmp_path, sourced_book({"Drawer": ("r.go::Level",), "PutItem": ("r.go::Put",)}), where, base, capsys)
    assert vias(found) == [("Level", "Drawer", "direct")]
    assert (found["plan"], found["fallbacks"]) == ("whole", [{"path": "r.go", "why": "record Drawer changed: the whole book"}])


def test_a_changed_symbol_nothing_mentions_and_no_element_names_is_uncovered(monkeypatch, tmp_path, capsys):
    z = "package shelf\n\nfunc Stray() int {\n\treturn 1\n}\n\nfunc Lone() int {\n\treturn Stray()\n}\n"
    where, base = scene(tmp_path, {"h.go": HANDLERS, "z.go": z})
    commit_files(where, {"z.go": z.replace("return 1", "return 2")})
    code, found, _ = affect(monkeypatch, tmp_path, sourced_book({"PutItem": ("h.go::Put",)}), where, base, capsys)
    assert (code, found["chains"], found["uncovered"]) == (1, [], [{"path": "z.go", "function": "Stray"}])


def test_a_function_in_a_file_no_element_names_reaches_the_element_that_mentions_it(monkeypatch, tmp_path, capsys):
    z = "package shelf\n\nfunc Stray() int {\n\treturn 1\n}\n"
    where, base = scene(tmp_path, {"h.go": HANDLERS, "z.go": z})
    commit_files(where, {"h.go": HANDLERS.replace("return help(id)\n}", "return help(id) + Stray()\n}"), "z.go": z.replace("return 1", "return 2")})
    code, found, _ = affect(monkeypatch, tmp_path, sourced_book({"PutItem": ("h.go::Put",)}), where, base, capsys)
    assert vias(found) == [("Put", "PutItem", "direct"), ("Stray", "PutItem", "through Stray")]
    assert (code, found["uncovered"]) == (0, [])


def test_a_screen_reaches_its_interactions_and_a_record_no_call():
    screen = type("Dashboard", (), {})
    service = cast("Service[Any]", SimpleNamespace(interactions=(SimpleNamespace(__name__="Tap", screen=screen, leads_to=None),
                                                                  SimpleNamespace(__name__="Idle", screen=None, leads_to=None))))
    assert calls_of(service, screen, "screen") == {"Tap"}
    assert calls_of(service, screen, "record") is None
    assert calls_of(service, screen, "event") is None


def test_a_screen_no_interaction_names_and_an_action_no_call_carries_reach_no_call():
    screen = type("Dashboard", (), {})
    other = type("Other", (), {})
    service = cast("Service[Any]", SimpleNamespace(interactions=(SimpleNamespace(__name__="Tap", screen=other, leads_to=None),), endpoints=(), outside=()))
    assert calls_of(service, screen, "screen") == set()
    assert calls_of(service, type("Sweep", (), {}), "action") == set()


def cabinet_book(sources: dict[str, tuple[str, ...]]) -> Any:
    book = sourced_book(sources)
    book.screens = (type("Cabinet", (Screen,), {"source": sources.get("Cabinet", ()), "__module__": __name__}),)
    return book


def test_a_screen_nothing_reaches_is_listed_as_unplayed_and_leaves_the_plan_partial(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    commit_files(where, {**edited("put.go", "return id", "return id + id"), **edited("drawer.go", "return 1", "return 2")})
    book = cabinet_book({"PutItem": ("put.go::Put",), "Cabinet": ("drawer.go::Open",)})
    code, found, out = affect(monkeypatch, tmp_path, book, where, base, capsys)
    assert (code, found["plan"], found["only"], found["fallbacks"]) == (0, "partial", ["PutItem"], [])
    assert found["unplayed"] == [{"element": "Cabinet", "kind": "screen", "path": "drawer.go"}]
    assert [c["plays"] for c in found["chains"] if c["element"] == "Cabinet"] == [[]]
    assert "unplayed (the book states them and no play reaches them):\n  screen Cabinet" in out
    assert "-> Cabinet (screen, direct) -> no play reaches it" in out


def test_a_diff_reaching_only_an_unplayed_screen_gives_the_plan_empty_and_exits_1(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    commit_files(where, edited("drawer.go", "return 1", "return 2"))
    code, found, out = affect(monkeypatch, tmp_path, cabinet_book({"Cabinet": ("drawer.go::Open",)}), where, base, capsys)
    assert (code, found["plan"], found["only"], found["fallbacks"], found["whole"]) == (1, "empty", [], [], False)
    assert [u["element"] for u in found["unplayed"]] == ["Cabinet"]
    assert "unplayed (the book states them and no play reaches them):" in out
    assert out.splitlines()[-1] == "nothing to play: the changed files select no play"


def test_an_action_no_call_carries_is_unplayed_and_does_not_make_the_plan_whole(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    commit_files(where, edited("put.go", "return id", "return id + id"))
    monkeypatch.setattr(affected_module, "carriers", lambda service, action: ([], []))
    code, found, _ = affect(monkeypatch, tmp_path, sourced_book({"Put": ("put.go::Put",)}), where, base, capsys)
    assert found["unplayed"] == [{"element": "Put", "kind": "action", "path": "put.go"}]
    assert (code, found["plan"], found["fallbacks"], found["only"]) == (1, "empty", [], [])


def test_run_only_accepts_an_outside_happening_and_keeps_the_journeys_that_arrange_it(monkeypatch, tmp_path, capsys):
    code, out = run_shelf(monkeypatch, shelf_book(journeys=(Haunting, Shelving, Clearing)), tmp_path, capsys, "--only", "Ghost")
    assert "only what calls Ghost: 1 of 3 journeys" in out
    assert "Haunting" in out
    assert "Shelving" not in out


def test_run_only_still_refuses_a_name_the_book_does_not_have(monkeypatch, tmp_path, capsys):
    with pytest.raises(SystemExit, match="--only names no endpoint or interaction or outside happening of shelf: Nobody"):
        run_shelf(monkeypatch, shelf_book(), tmp_path, capsys, "--only", "Nobody")


IFACE = ("package shelf\n\ntype Repository interface {\n\tCreate(id string) error\n}\n\n"
         "func Use(r Repository) error {\n\treturn r.Get()\n}\n\n"
         "func (s *Service) Create(id string) error {\n\treturn nil\n}\n\n"
         "func Put() error {\n\treturn Use(nil)\n}\n")
HOLDS = ("package shelf\n\nconst Limit = 5\n\ntype Box struct {\n\tMax int `json:\"max\"`\n\tLimit int\n}\n\n"
         "func Make() Box {\n\treturn Box{}\n}\n\nfunc Cap() int {\n\treturn Limit\n}\n")


def test_an_interface_declaring_the_changed_method_name_does_not_pull_in_the_functions_that_mention_it(monkeypatch, tmp_path, capsys):
    where, base = scene(tmp_path, {"s.go": IFACE})
    commit_files(where, {"s.go": IFACE.replace("return nil", "return fmt.Errorf(id)")})
    book = sourced_book({"PutItem": ("s.go::Put",), "RestockItem": ("s.go::Use",), "RemoveItem": ("s.go::Service.Create",)})
    _, found, _ = affect(monkeypatch, tmp_path, book, where, base, capsys)
    assert found["only"] == ["RemoveItem"]


def test_a_struct_mentioning_a_changed_constant_does_not_pull_in_its_users_but_a_function_does(monkeypatch, tmp_path, capsys):
    where, base = scene(tmp_path, {"b.go": HOLDS})
    commit_files(where, {"b.go": HOLDS.replace("Limit = 5", "Limit = 6")})
    book = sourced_book({"PutItem": ("b.go::Make",), "RemoveItem": ("b.go::Cap",)})
    _, found, _ = affect(monkeypatch, tmp_path, book, where, base, capsys)
    assert vias(found) == [("Limit", "RemoveItem", "through Limit")]


def test_a_changed_type_still_reaches_every_function_that_mentions_it(monkeypatch, tmp_path, capsys):
    where, base = scene(tmp_path, {"b.go": HOLDS})
    commit_files(where, {"b.go": HOLDS.replace("Max int", "Max int64")})
    book = sourced_book({"PutItem": ("b.go::Make",), "RemoveItem": ("b.go::Cap",)})
    _, found, _ = affect(monkeypatch, tmp_path, book, where, base, capsys)
    assert vias(found) == [("Box", "PutItem", "through Box")]


PYCLASS = ("def helper():\n    return 1\n\n\nclass Shelf:\n    def put(self):\n        return helper()\n\n\n"
           "def caller():\n    return put()\n\n\ndef other():\n    return 2\n")


def test_a_python_class_does_not_join_by_mention_but_its_method_and_the_methods_callers_do(monkeypatch, tmp_path, capsys):
    where, base = scene(tmp_path, {"s.py": PYCLASS})
    commit_files(where, {"s.py": PYCLASS.replace("return 1", "return 3")})
    book = sourced_book({"Drawer": ("s.py::Shelf",), "PutItem": ("s.py::put",), "RestockItem": ("s.py::caller",), "RemoveItem": ("s.py::other",)})
    _, found, _ = affect(monkeypatch, tmp_path, book, where, base, capsys)
    assert vias(found) == [("helper", "PutItem", "through helper"), ("helper", "RestockItem", "through put")]


ROUTE = "export function load() {{\n\treturn actions();\n}}\n\nexport function actions() {{\n\treturn {n};\n}}\n"
BYSTANDER = "export function other() {\n\treturn actions();\n}\n"


def test_a_route_file_that_defines_the_name_binds_its_mentions_to_its_own_definition(monkeypatch, tmp_path, capsys):
    files = {"routes/a/page.ts": ROUTE.format(n=1), "routes/b/page.ts": ROUTE.format(n=1)}
    where, base = scene(tmp_path, files)
    commit_files(where, {"routes/a/page.ts": ROUTE.format(n=2)})
    book = sourced_book({"PutItem": ("routes/a/page.ts::load",), "RestockItem": ("routes/b/page.ts::load",)})
    _, found, _ = affect(monkeypatch, tmp_path, book, where, base, capsys)
    assert vias(found) == [("actions", "PutItem", "through actions")]


def test_a_file_that_does_not_define_the_name_still_reaches_every_definition(monkeypatch, tmp_path, capsys):
    files = {"routes/a/page.ts": ROUTE.format(n=1), "routes/b/page.ts": ROUTE.format(n=1), "lib/o.ts": BYSTANDER}
    where, base = scene(tmp_path, files)
    commit_files(where, {"routes/a/page.ts": ROUTE.format(n=2)})
    book = sourced_book({"PutItem": ("routes/a/page.ts::load",), "RestockItem": ("routes/b/page.ts::load",), "RemoveItem": ("lib/o.ts::other",)})
    _, found, _ = affect(monkeypatch, tmp_path, book, where, base, capsys)
    assert {c["element"] for c in found["chains"]} == {"PutItem", "RemoveItem"}
    commit_files(where, {"routes/b/page.ts": ROUTE.format(n=3)})
    _, found, _ = affect(monkeypatch, tmp_path, book, where, base, capsys)
    assert {c["element"] for c in found["chains"] if c["function"] == "actions"} == {"PutItem", "RestockItem", "RemoveItem"}


MAKER = "package shelf\n\nfunc Make() string {\n\treturn helper()\n}\n"
HELPER = "package shelf\n\nfunc helper() string {\n\treturn \"a\"\n}\n"


def test_a_go_package_binds_a_mention_to_the_definition_in_another_file_of_the_package(monkeypatch, tmp_path, capsys):
    where, base = scene(tmp_path, {"p/make.go": MAKER, "p/helper.go": HELPER})
    commit_files(where, {"p/helper.go": HELPER.replace('"a"', '"z"')})
    book = sourced_book({"PutItem": ("p/make.go::Make",)})
    _, found, _ = affect(monkeypatch, tmp_path, book, where, base, capsys)
    assert vias(found) == [("helper", "PutItem", "through helper")]


def test_a_go_package_with_its_own_definition_does_not_reach_the_helper_of_another_package(monkeypatch, tmp_path, capsys):
    files = {"p/make.go": MAKER, "p/helper.go": HELPER, "q/make.go": MAKER.replace("shelf", "drawer"), "q/helper.go": HELPER.replace("shelf", "drawer")}
    where, base = scene(tmp_path, files)
    commit_files(where, {"p/helper.go": HELPER.replace('"a"', '"z"')})
    book = sourced_book({"PutItem": ("p/make.go::Make",), "RestockItem": ("q/make.go::Make",)})
    _, found, _ = affect(monkeypatch, tmp_path, book, where, base, capsys)
    assert vias(found) == [("helper", "PutItem", "through helper")]


def test_a_method_name_mentioned_from_another_file_still_joins(monkeypatch, tmp_path, capsys):
    getter = "package shelf\n\nfunc (s *Service) Get() string {\n\treturn \"a\"\n}\n"
    user = "package drawer\n\nfunc Get() string {\n\treturn \"b\"\n}\n\nfunc Use(s *Service) string {\n\treturn s.Get()\n}\n"
    where, base = scene(tmp_path, {"a/get.go": getter, "b/use.go": user})
    commit_files(where, {"a/get.go": getter.replace('"a"', '"z"')})
    book = sourced_book({"PutItem": ("b/use.go::Use",)})
    _, found, _ = affect(monkeypatch, tmp_path, book, where, base, capsys)
    assert vias(found) == [("Service.Get", "PutItem", "through Service.Get")]
