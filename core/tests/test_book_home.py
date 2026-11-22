"""Where a book lives: the artifacts folder unless the repository's agents.yml keeps it in the repository."""

from __future__ import annotations

import pytest

from stablemate_core import books
from stablemate_core import config as cfgmod
from stablemate_core.config import ConfigError

from test_run_checkouts import _repo, _tree

BRANCH = "run/coder-t"
IN_REPO = "book:\n  home: repo\n"


def _unmoved(folder, layout="services/old/service.py", text="from ostler.book import Service\n"):
    target = folder / layout
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


@pytest.fixture
def world(tmp_path, monkeypatch, cfg_file):
    monkeypatch.setenv(cfgmod.ARTIFACTS_DIR_ENV, str(tmp_path / "artifacts"))
    artifacts = _repo(tmp_path / "artifacts")
    code = _repo(tmp_path / "acme-app")
    return {"artifacts": artifacts, "code": code, "trees": tmp_path / "trees"}


def test_a_repository_with_no_key_reads_its_book_in_the_artifacts_dir(world):
    assert books.book_home(world["code"]) == world["artifacts"]
    assert books.book_in_repo(world["code"]) is False


def test_book_home_repo_is_the_folder_of_the_nearest_agents_yml(world):
    code = world["code"]
    (code / "agents.yml").write_text(IN_REPO)
    deep = code / "pkg" / "inner"
    deep.mkdir(parents=True)

    assert books.book_home(deep) == code
    assert books.book_in_repo(deep) is True


def test_a_nested_agents_yml_with_the_key_is_its_own_book_root(world):
    code = world["code"]
    nested = code / "tools" / "demo"
    nested.mkdir(parents=True)
    (nested / "agents.yml").write_text(IN_REPO)

    assert books.book_home(nested) == nested
    assert books.book_home(code) == world["artifacts"]


def test_the_walk_for_agents_yml_stops_at_the_repository_top(world, tmp_path):
    (tmp_path / "agents.yml").write_text(IN_REPO)

    assert books.book_settings(world["code"]).folder == world["code"]
    assert books.book_home(world["code"]) == world["artifacts"]


def test_the_artifacts_worktree_on_the_starts_branch_is_the_book_root(world):
    book = _tree(world["artifacts"], world["trees"])
    code = _tree(world["code"], world["trees"])

    assert books.book_home(code) == book


def test_a_branch_with_no_artifacts_worktree_reads_the_artifacts_dir(world):
    code = _tree(world["code"], world["trees"])

    assert books.book_home(code) == world["artifacts"]


def test_a_start_in_the_artifacts_repo_or_its_worktree_is_its_own_checkout(world):
    book = _tree(world["artifacts"], world["trees"])

    assert books.book_home(world["artifacts"]) == world["artifacts"]
    assert books.book_home(book) == book


def test_a_start_under_an_artifacts_dir_that_is_no_repository_is_that_dir(tmp_path, monkeypatch, cfg_file):
    plain = tmp_path / "plain-artifacts"
    (plain / "services").mkdir(parents=True)
    monkeypatch.setenv(cfgmod.ARTIFACTS_DIR_ENV, str(plain))

    assert books.book_home(plain / "services") == plain


def test_a_workspace_member_follows_the_same_rule(world, cfg_file):
    code = world["code"]
    cfg_file.write_text(f'[workspaces]\nacme = [{{ path = "{code}", name = "app" }}]\n')
    book = _tree(world["artifacts"], world["trees"])
    tree = _tree(code, world["trees"])

    assert books.book_home(code) == world["artifacts"]
    assert books.book_home(tree) == book


def test_the_artifacts_dir_inside_a_member_follows_the_enclosing_repository(tmp_path, monkeypatch, cfg_file):
    member = _repo(tmp_path / "member")
    inner = member / "artifacts"
    inner.mkdir()
    monkeypatch.setenv(cfgmod.ARTIFACTS_DIR_ENV, str(inner))
    cfg_file.write_text(f'[workspaces]\nacme = [{{ path = "{member}", name = "member" }}]\n')
    linked = _tree(member, tmp_path / "linked")
    linked_inner = linked / "artifacts"
    linked_inner.mkdir(exist_ok=True)

    assert books.book_home(linked) == linked_inner


def test_an_unmoved_book_is_refused_naming_both_ways_out(world):
    code = world["code"]
    _unmoved(code)

    with pytest.raises(books.UnmovedBook) as raised:
        books.book_home(code)

    message = str(raised.value)
    assert isinstance(raised.value, ConfigError)
    assert f"{code}/agents.yml" in message
    assert "home: repo" in message
    assert str(world["artifacts"]) in message
    assert "docs/guide/moving-a-book-to-the-artifacts-folder.md" in message


def test_an_unmoved_book_is_accepted_once_the_key_is_set(world):
    code = world["code"]
    _unmoved(code)
    (code / "agents.yml").write_text(IN_REPO)

    assert books.book_home(code) == code


@pytest.mark.parametrize(
    "layout, text",
    [
        ("services/user/service.py", "class UserService: ...\n"),
        ("services/user/__init__.py", "from ostler.book import Service\n"),
    ],
)
def test_a_services_folder_without_an_ostler_book_is_not_refused(world, layout, text):
    code = world["code"]
    _unmoved(code, layout, text)

    assert books.unmoved_book(code) is None
    assert books.book_home(code) == world["artifacts"]


def test_a_surface_split_unmoved_book_is_refused(world):
    code = world["code"]
    _unmoved(code, "services/groom/http/service.py")

    with pytest.raises(books.UnmovedBook):
        books.book_home(code)


def test_book_checkouts_names_a_lone_repository_by_its_repository_name(world):
    code = world["code"]

    assert books.book_checkouts(code) == {cfgmod.repository_name(code): code}


def test_book_checkouts_keeps_workspace_members(world, cfg_file):
    code = world["code"]
    other = _repo(world["code"].parent / "web")
    cfg_file.write_text(
        f'[workspaces]\nacme = [{{ path = "{code}", name = "app" }}, {{ path = "{other}", name = "web" }}]\n'
    )

    assert books.book_checkouts(code) == {"app": code, "web": other}


def test_book_checkouts_adds_nothing_for_the_artifacts_repo(world):
    assert books.book_checkouts(world["artifacts"]) == {}


def test_the_product_defaults_to_the_repository_name(world):
    code = world["code"]

    assert books.book_settings(code).product == cfgmod.repository_name(code)
    assert books.book_product(code) == cfgmod.repository_name(code)


def test_book_product_overrides_it(world):
    code = world["code"]
    (code / "agents.yml").write_text("book:\n  product: globex\n")

    assert books.book_product(code) == "globex"


def test_book_product_is_none_in_the_artifacts_repo(world):
    assert books.book_product(world["artifacts"]) is None


def test_product_folder_is_products_name_in_artifacts_and_product_beside_services_in_repo(world):
    code = world["code"]
    name = cfgmod.repository_name(code)

    assert books.product_folder(code) == world["artifacts"] / "products" / name
    assert books.product_folder(world["artifacts"]) is None

    (code / "agents.yml").write_text(IN_REPO)

    assert books.product_folder(code) == code / "product"


def test_a_repository_with_no_key_names_its_books_under_its_repository_folder(world):
    code = world["code"]

    assert books.service_package(code) == "services.acme-app"
    assert books.service_module(code, "api") == "services.acme-app.api"
    assert books.service_folder(code, "api") == "services/acme-app/api"


def test_a_repository_that_keeps_its_book_names_its_books_under_services(world):
    code = world["code"]
    (code / "agents.yml").write_text(IN_REPO)

    assert books.service_package(code) == "services"
    assert books.service_module(code, "api") == "services.api"
    assert books.service_folder(code, "api") == "services/api"


def test_started_in_the_artifacts_folder_the_package_holds_every_repository(world):
    assert books.service_package(world["artifacts"]) == "services"


def test_the_artifacts_folder_and_its_worktree_are_namespaced(world):
    book = _tree(world["artifacts"], world["trees"])

    assert books.namespaced(world["artifacts"]) is True
    assert books.namespaced(book) is True
    assert books.namespaced(world["code"]) is False


def test_package_folder_turns_dots_into_slashes():
    assert books.package_folder("services.acme-app") == "services/acme-app"
    assert books.package_folder("services") == "services"
