"""The company, team and product books: rules above any one service, searched beside the service books."""

from __future__ import annotations

import contextlib
import io
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator

import pytest

from book_fakes import isolated_services
from conftest import keep_book_in_repo
from ostler._vendor.stablemate_core import book_branch
from ostler._vendor.stablemate_core import config as core_config
from ostler.book.pages import cmd_pages
from ostler.book.index import cmd_search_book

SHOP = '''
from ostler.book import Action, Arrange, Service, Stack
from ostler.book.domain import State


class Order(Action):
    """Opens a ceramic order."""


class Opens(Arrange[int]):
    does = "A customer opens a ceramic order."
    carries = Order


service = Service(name="shop", new_model=State, surface=lambda environment: None, journeys=(),
                  stack=lambda directory: Stack((), directory), outside=(Opens,))
'''

GLAZE = "date: 2026-11-21\nsources: operator, 2026-11-21\n\nA glaze is a ceramic coating fired onto a piece.\nIt is never a paint.\n"
KILN = "date: 2026-11-20\n\nA kiln fires the ceramic piece twice.\n"
SLIP = "date: 2026-11-19\nstatus: superseded by kiln\n\nA slip is a ceramic clay in water.\n"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _shop(root: Path) -> None:
    _write(root / "services" / "__init__.py", "")
    _write(root / "services" / "shop" / "__init__.py", "")
    _write(root / "services" / "shop" / "service.py", SHOP)


def _product(root: Path, slug: str, text: str) -> None:
    _write(root / "product" / f"{slug}.md", text)


def _team(artifacts: Path, team: str, slug: str, text: str) -> None:
    _write(artifacts / "teams" / team / f"{slug}.md", text)


def _company(artifacts: Path, slug: str, text: str) -> None:
    _write(artifacts / "company" / f"{slug}.md", text)


def _on_team(root: Path, team: str) -> None:
    _write(root / "agents.yml", f"book:\n  home: repo\n  team: {team}\n")


@pytest.fixture
def artifacts(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path_factory.mktemp("artifacts")
    monkeypatch.setenv(core_config.ARTIFACTS_DIR_ENV, str(folder))
    return folder.resolve()


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, artifacts: Path) -> Iterator[Path]:
    keep_book_in_repo(tmp_path)
    for tmp in isolated_services(tmp_path, monkeypatch):
        _shop(tmp)
        yield tmp


def _search(term: str, service: str | None = None, kind: str | None = None) -> int:
    return cmd_search_book(SimpleNamespace(service=service, term=term, kind=kind))


def _all_levels(root: Path, artifacts: Path) -> None:
    _on_team(root, "glaze-lab")
    _company(artifacts, "words", "date: 2026-11-01\n\nA ceramic is named in the singular.\n")
    _team(artifacts, "glaze-lab", "firing", "date: 2026-11-02\nstatus: accepted\n\nA ceramic is fired twice.\n")
    _product(root, "glaze", GLAZE)


def test_search_finds_a_product_page_with_no_service(root: Path, capsys: pytest.CaptureFixture[str]):
    _product(root, "glaze", GLAZE)
    assert _search("fired onto") == 0
    out = capsys.readouterr().out
    assert "== product\n" in out
    assert "product   product/glaze.md:4\n    A glaze is a ceramic coating fired onto a piece.\n" in out


def test_search_finds_every_level_with_no_service(root: Path, artifacts: Path, capsys: pytest.CaptureFixture[str]):
    _all_levels(root, artifacts)
    assert _search("ceramic") == 0
    out = capsys.readouterr().out
    assert "== company\n" in out
    assert "company   company/words.md:3" in out
    assert "== team glaze-lab\n" in out
    assert "team      teams/glaze-lab/firing.md:4" in out
    assert "== product\n" in out
    assert "product   product/glaze.md:4" in out


def test_search_finds_every_level_when_a_service_is_given(root: Path, artifacts: Path, capsys: pytest.CaptureFixture[str]):
    _all_levels(root, artifacts)
    assert _search("ceramic", service="services.shop") == 0
    out = capsys.readouterr().out
    assert "== company\n" in out
    assert "== team glaze-lab\n" in out
    assert "== product\n" in out
    assert "action" in out


def test_levels_print_company_then_team_then_product_then_the_services(root: Path, artifacts: Path, capsys: pytest.CaptureFixture[str]):
    _all_levels(root, artifacts)
    assert _search("ceramic") == 0
    headings = [line for line in capsys.readouterr().out.splitlines() if line.startswith("== ")]
    assert headings == ["== company", "== team glaze-lab", "== product", "== services.shop"]


def test_no_team_in_agents_yml_leaves_the_team_folder_unread(root: Path, artifacts: Path, capsys: pytest.CaptureFixture[str]):
    _team(artifacts, "glaze-lab", "firing", "date: 2026-11-02\n\nA ceramic is fired twice.\n")
    assert _search("fired twice") == 1
    assert "teams/" not in capsys.readouterr().out


def test_another_teams_folder_is_never_read(root: Path, artifacts: Path, capsys: pytest.CaptureFixture[str]):
    _on_team(root, "glaze-lab")
    _team(artifacts, "kiln-crew", "firing", "date: 2026-11-02\n\nA ceramic is fired twice.\n")
    assert _search("fired twice") == 1
    assert "kiln-crew" not in capsys.readouterr().out


def test_missing_folders_change_nothing(root: Path, capsys: pytest.CaptureFixture[str]):
    _on_team(root, "glaze-lab")
    assert _search("ceramic") == 0
    out = capsys.readouterr().out
    assert [line for line in out.splitlines() if line.startswith("== ")] == ["== services.shop"]


@pytest.mark.parametrize("level,heading", [("company", "== company"), ("team", "== team glaze-lab"), ("product", "== product")])
def test_each_level_kind_shows_only_that_level(root: Path, artifacts: Path, capsys: pytest.CaptureFixture[str], level: str, heading: str):
    _all_levels(root, artifacts)
    assert _search("ceramic", kind=level) == 0
    out = capsys.readouterr().out
    assert [line for line in out.splitlines() if line.startswith("== ")] == [heading]
    assert "action" not in out


def test_the_decision_kind_excludes_every_level(root: Path, artifacts: Path, capsys: pytest.CaptureFixture[str]):
    _all_levels(root, artifacts)
    assert _search("ceramic", kind="decision") == 1
    out = capsys.readouterr().out
    assert "== " not in out


def test_a_superseded_page_is_found_and_marked(root: Path, capsys: pytest.CaptureFixture[str]):
    _product(root, "slip", SLIP)
    assert _search("clay in water") == 0
    assert "product   product/slip.md:4 (superseded)\n" in capsys.readouterr().out


def test_no_wider_folder_leaves_the_output_unchanged(root: Path, capsys: pytest.CaptureFixture[str]):
    assert _search("ceramic") == 0
    out = capsys.readouterr().out
    assert "product" not in out.replace("nothing in the book says", "")
    assert "== services.shop" in out


def test_check_is_red_on_a_page_without_a_date(root: Path, capsys: pytest.CaptureFixture[str]):
    _product(root, "glaze", GLAZE)
    _product(root, "kiln", "sources: operator\n\nA kiln fires the piece.\n")
    assert cmd_pages(SimpleNamespace(check=True, level=None), str(root)) == 1
    out = capsys.readouterr().out
    assert "product/kiln.md has no date: line" in out
    assert "glaze" not in out


def test_check_is_red_on_an_empty_body_in_a_company_page(root: Path, artifacts: Path, capsys: pytest.CaptureFixture[str]):
    _company(artifacts, "kiln", "date: 2026-11-21\n\n")
    assert cmd_pages(SimpleNamespace(check=True, level=None), str(root)) == 1
    assert "company/kiln.md has an empty body" in capsys.readouterr().out


def test_check_is_green_on_complete_pages(root: Path, artifacts: Path, capsys: pytest.CaptureFixture[str]):
    _all_levels(root, artifacts)
    assert cmd_pages(SimpleNamespace(check=True, level=None), str(root)) == 0
    assert capsys.readouterr().out == ""


def test_the_list_names_each_page_in_level_order(root: Path, artifacts: Path, capsys: pytest.CaptureFixture[str]):
    _all_levels(root, artifacts)
    _product(root, "slip", SLIP)
    assert cmd_pages(SimpleNamespace(check=False, level=None), str(root)) == 0
    assert capsys.readouterr().out.splitlines() == [
        "company  words  2026-11-01  A ceramic is named in the singular.",
        "team  firing  2026-11-02  accepted  A ceramic is fired twice.",
        "product  glaze  2026-11-21  A glaze is a ceramic coating fired onto a piece.",
        "product  slip  2026-11-19  superseded by kiln  A slip is a ceramic clay in water.",
    ]


def test_the_list_takes_one_level(root: Path, artifacts: Path, capsys: pytest.CaptureFixture[str]):
    _all_levels(root, artifacts)
    assert cmd_pages(SimpleNamespace(check=False, level="team"), str(root)) == 0
    assert capsys.readouterr().out.splitlines() == ["team  firing  2026-11-02  accepted  A ceramic is fired twice."]


def _code_repo(parent: Path, name: str, manifest: str = "") -> Path:
    folder = parent / name
    folder.mkdir()
    subprocess.run(["git", "init", "-q", str(folder)], check=True)
    if manifest:
        _write(folder / "agents.yml", manifest)
    return folder


def _in_products(artifacts: Path, product: str, slug: str, text: str) -> None:
    _write(artifacts / "products" / product / f"{slug}.md", text)


def _listed(level: str | None = None) -> list[str]:
    return [line for line in _pages_out(level)]


def _pages_out(level: str | None) -> list[str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        assert cmd_pages(SimpleNamespace(check=False, level=level)) == 0
    return buffer.getvalue().splitlines()


def test_pages_from_a_lone_repository_list_its_product_folder_only(tmp_path: Path, artifacts: Path, monkeypatch: pytest.MonkeyPatch):
    repo = _code_repo(tmp_path, "acme")
    _in_products(artifacts, "acme", "glaze", GLAZE)
    _in_products(artifacts, "globex", "kiln", KILN)
    monkeypatch.chdir(repo)
    assert _listed() == ["product  glaze  2026-11-21  A glaze is a ceramic coating fired onto a piece."]


def test_pages_from_the_artifacts_folder_list_every_product(artifacts: Path, monkeypatch: pytest.MonkeyPatch):
    _in_products(artifacts, "acme", "glaze", GLAZE)
    _in_products(artifacts, "globex", "kiln", KILN)
    monkeypatch.chdir(artifacts)
    assert _listed("product") == [
        "product  glaze  2026-11-21  A glaze is a ceramic coating fired onto a piece.",
        "product  kiln  2026-11-20  A kiln fires the ceramic piece twice.",
    ]


def test_book_product_overrides_the_repository_name(tmp_path: Path, artifacts: Path, monkeypatch: pytest.MonkeyPatch):
    repo = _code_repo(tmp_path, "acme", "book:\n  product: globex\n")
    _in_products(artifacts, "acme", "glaze", GLAZE)
    _in_products(artifacts, "globex", "kiln", KILN)
    monkeypatch.chdir(repo)
    assert _listed() == ["product  kiln  2026-11-20  A kiln fires the ceramic piece twice."]


def test_team_is_read_from_the_code_repository_manifest(tmp_path: Path, artifacts: Path, monkeypatch: pytest.MonkeyPatch):
    repo = _code_repo(tmp_path, "acme", "book:\n  team: glaze-lab\n")
    _team(artifacts, "glaze-lab", "firing", "date: 2026-11-02\nstatus: accepted\n\nA ceramic is fired twice.\n")
    monkeypatch.chdir(repo)
    assert _listed("team") == ["team  firing  2026-11-02  accepted  A ceramic is fired twice."]


def test_search_heading_names_the_product(tmp_path: Path, artifacts: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    repo = _code_repo(tmp_path, "acme")
    _in_products(artifacts, "acme", "glaze", GLAZE)
    (artifacts / "services").mkdir()
    monkeypatch.chdir(repo)
    assert _search("fired onto") == 0
    out = capsys.readouterr().out
    assert "== product acme\n" in out
    assert "product   products/acme/glaze.md:4\n" in out


def _git(folder: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(folder), *args], check=True, capture_output=True)


def _committed_repo(folder: Path) -> Path:
    folder.mkdir(parents=True)
    _git(folder, "init", "--quiet", "-b", "main")
    _git(folder, "commit", "--quiet", "--allow-empty", "-m", "x")
    return folder.resolve()


@pytest.fixture
def branched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    config_file = tmp_path / "config.toml"
    config_file.write_text(f'worktree_dir = "{tmp_path / "trees"}"\n')
    monkeypatch.setenv(core_config.CONFIG_PATH_ENV, str(config_file))
    artifacts = _committed_repo(tmp_path / "artifacts-repo")
    monkeypatch.setenv(core_config.ARTIFACTS_DIR_ENV, str(artifacts))
    code = _committed_repo(tmp_path / "acme")
    _git(code, "worktree", "add", "--quiet", "-b", "feat/x", str(tmp_path / "acme-x"))
    on_branch = (tmp_path / "acme-x").resolve()
    book = book_branch.open_book_branch(on_branch)
    _in_products(book, "acme", "glaze", GLAZE)
    _git(book, "add", "products")
    _git(book, "commit", "--quiet", "-m", "add a product page")
    (book / "services").mkdir()
    return {"base": code, "branch": on_branch, "book": book}


def test_pages_from_a_checkout_on_a_book_branch_list_the_page_committed_there(branched: dict[str, Path], monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(branched["branch"])
    assert _listed() == ["product  glaze  2026-11-21  A glaze is a ceramic coating fired onto a piece."]


def test_search_from_a_checkout_on_a_book_branch_names_the_product(branched: dict[str, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    monkeypatch.chdir(branched["branch"])
    assert _search("fired onto") == 0
    out = capsys.readouterr().out
    assert "== product acme\n" in out
    assert "products/acme/glaze.md:4" in out


def test_pages_from_a_checkout_on_the_base_branch_leave_out_the_branch_page(branched: dict[str, Path], monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(branched["base"])
    assert _listed() == []


def test_pages_from_an_artifacts_worktree_list_that_checkouts_products(branched: dict[str, Path], monkeypatch: pytest.MonkeyPatch):
    _in_products(branched["book"], "globex", "kiln", KILN)
    monkeypatch.chdir(branched["book"])
    assert _listed("product") == [
        "product  glaze  2026-11-21  A glaze is a ceramic coating fired onto a piece.",
        "product  kiln  2026-11-20  A kiln fires the ceramic piece twice.",
    ]
