"""`ostler book move` puts a flat book into its repository's folder of the artifacts folder and rewrites the module names."""

from __future__ import annotations

from pathlib import Path

import pytest
from book_fakes import git as _git
from conftest import write
from ostler.book import cli
from test_book_home_resolution import _artifacts, _lone_repository

BOOK = "from ostler.book import Service\n"


def _flat(root: Path, name: str, **files: str) -> None:
    write(root / "services" / name / "service.py", BOOK)
    for relative, text in files.items():
        write(root / "services" / name / relative, text)


def _tree(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in sorted(root.rglob("*")) if p.is_file()}


def _move(monkeypatch, cwd: Path, *arguments: str) -> int:
    monkeypatch.chdir(cwd)
    return cli.main(["move", *arguments])


def test_a_flat_book_moves_into_its_repository_folder_with_its_module_names_rewritten(tmp_path, monkeypatch, capsys):
    artifacts = _artifacts()
    _flat(artifacts, "api", **{"index.tsv": "services.api.endpoints:Ping\tendpoint\tPing\n", "decisions/one.md": "The services.api book says so.\n"})
    write(artifacts / "services/web/foreign.py", 'Foreign("x", owner="services.api")\n')
    write(artifacts / "services/api/__pycache__/service.cpython-312.pyc", "x")

    assert _move(monkeypatch, tmp_path, "api", "--repo", "acme") == 0

    out = capsys.readouterr().out
    assert (artifacts / "services/acme/api/service.py").read_text() == BOOK
    assert not (artifacts / "services/api").exists()
    assert (artifacts / "services/__init__.py").read_text() == ""
    assert not list((artifacts / "services").rglob("__pycache__"))
    assert (artifacts / "services/web/foreign.py").read_text() == 'Foreign("x", owner="services.acme.api")\n'
    assert not (artifacts / "services/acme/api/index.tsv").exists()
    assert (artifacts / "services/acme/api/decisions/one.md").read_text() == "The services.acme.api book says so.\n"
    assert "moved services/api to services/acme/api" in out
    assert "rewrote 1 reference(s) in services/web/foreign.py" in out
    assert "index.tsv" not in out


def test_text_that_is_not_a_module_path_is_left_alone(tmp_path, monkeypatch, capsys):
    artifacts = _artifacts()
    _flat(artifacts, "api")
    notes = (
        'URL = "/services/api"\n'
        'POINTER = "source=services/api/handler.py::Handler"\n'
        'PLURAL = "services.apis"\n'
        'PREFIXED = "my_services.api"\n'
        'NESTED = "x.services.api"\n'
        'TYPED = "::services.api"\n'
    )
    write(artifacts / "services/web/notes.py", notes)

    assert _move(monkeypatch, tmp_path, "api", "--repo", "acme") == 0

    out = capsys.readouterr().out
    assert (artifacts / "services/web/notes.py").read_text() == notes
    assert "rewrote" not in out
    assert 'check by hand: services/web/notes.py:2: POINTER = "source=services/api/handler.py::Handler"' in out
    assert out.count("check by hand") == 1


def test_an_absolute_import_is_rewritten_for_a_repository_whose_name_is_an_identifier(tmp_path, monkeypatch):
    artifacts = _artifacts()
    _flat(artifacts, "api")
    write(artifacts / "services/web/client.py", "from services.api.endpoints import Ping\nimport services.api\n")

    assert _move(monkeypatch, tmp_path, "api", "--repo", "acme_app") == 0

    assert (artifacts / "services/web/client.py").read_text() == "from services.acme_app.api.endpoints import Ping\nimport services.acme_app.api\n"


def test_an_absolute_import_refuses_the_move_into_a_hyphenated_repository_and_changes_nothing(tmp_path, monkeypatch, capsys):
    artifacts = _artifacts()
    _flat(artifacts, "api")
    write(artifacts / "services/web/client.py", "from services.api.endpoints import Ping\n")
    before = _tree(artifacts)

    assert _move(monkeypatch, tmp_path, "api", "--repo", "acme-app") == 2

    err = capsys.readouterr().err
    assert "services/web/client.py:1" in err
    assert "write it as a relative import first: no import statement can spell services.acme-app" in err
    assert _tree(artifacts) == before


def test_an_existing_target_refuses_the_move(tmp_path, monkeypatch, capsys):
    artifacts = _artifacts()
    _flat(artifacts, "api")
    write(artifacts / "services/acme/api/service.py", BOOK)
    before = _tree(artifacts)

    assert _move(monkeypatch, tmp_path, "api", "--repo", "acme") == 2

    assert "services/acme/api" in capsys.readouterr().err
    assert _tree(artifacts) == before


def test_a_book_named_like_its_repository_moves_one_folder_down(tmp_path, monkeypatch):
    artifacts = _artifacts()
    _flat(artifacts, "billing", **{"index.tsv": "services.billing.endpoints:Ping\tendpoint\tPing\n"})

    assert _move(monkeypatch, tmp_path, "billing", "--repo", "billing") == 0

    assert (artifacts / "services/billing/billing/service.py").read_text() == BOOK
    assert not (artifacts / "services/billing/billing/index.tsv").exists()
    assert not (artifacts / "services/billing/service.py").exists()
    assert not list((artifacts / "services").glob(".*"))


def test_a_whole_services_folder_moves_from_a_code_repository(tmp_path, monkeypatch, capsys):
    code = _lone_repository(tmp_path)
    write(code / "services/__init__.py", "")
    _flat(code, "api", **{"owner.py": 'OWNER = "services.shared"\n'})
    write(code / "services/ops/stack.yml", "name: acme\n")
    write(code / "services/shared/helpers.py", "X = 1\n")
    write(code / "services/__pycache__/x.pyc", "x")
    artifacts = _artifacts()

    assert _move(monkeypatch, code, "--from", "services") == 0

    out = capsys.readouterr().out
    assert sorted(p.name for p in (artifacts / "services/acme").iterdir()) == ["__init__.py", "api", "ops", "shared"]
    assert (artifacts / "services/__init__.py").exists()
    assert (artifacts / "services/acme/api/owner.py").read_text() == 'OWNER = "services.acme.shared"\n'
    assert not (code / "services/api").exists()
    assert f"moved {code / 'services/api'} to services/acme/api" in out


def test_a_slash_path_is_listed_for_a_hand_check(tmp_path, monkeypatch, capsys):
    artifacts = _artifacts()
    _flat(artifacts, "api", **{"service.md": "x\nsee services/api/handler.py for it\n"})

    assert _move(monkeypatch, tmp_path, "api", "--repo", "acme") == 0

    assert "check by hand: services/acme/api/service.md:2: see services/api/handler.py for it" in capsys.readouterr().out
    assert (artifacts / "services/acme/api/service.md").read_text() == "x\nsee services/api/handler.py for it\n"


def test_a_book_in_a_worktree_of_the_artifacts_repository_moves_in_that_worktree(tmp_path, monkeypatch):
    artifacts = _artifacts()
    _git(artifacts, "init", "--quiet", "-b", "main")
    _flat(artifacts, "api")
    _git(artifacts, "add", "-A")
    _git(artifacts, "commit", "--quiet", "-m", "init")
    tree = tmp_path / "trees" / "book"
    _git(artifacts, "worktree", "add", "--quiet", "-b", "feat/x", str(tree))

    assert _move(monkeypatch, tree, "api", "--repo", "acme") == 0

    assert (tree / "services/acme/api/service.py").exists()
    assert not (tree / "services/api").exists()
    assert (artifacts / "services/api/service.py").exists()
    assert not (artifacts / "services/acme").exists()


def test_to_names_the_artifacts_checkout_to_write_into(tmp_path, monkeypatch):
    other = tmp_path / "other"
    _flat(other, "api")

    assert _move(monkeypatch, tmp_path, "api", "--repo", "acme", "--to", str(other)) == 0

    assert (other / "services/acme/api/service.py").exists()
    assert not (_artifacts() / "services").exists()


def test_configuration_files_follow_the_move_and_the_checks_file_names_the_slash_path_too(tmp_path, monkeypatch, capsys):
    artifacts = _artifacts()
    _flat(artifacts, "api", **{"ops/stack.toml": 'book = "services.api"\n', "ops/templates/a.j2": "{{ services.api }}\n"})
    write(artifacts / "services/web/stack.yml", "owner: services.api\npath: services/api/x\n")
    write(artifacts / "services/web/stack.yaml", "owner: services.api\n")
    write(artifacts / ".agent-checks.toml", 'book = "services.api"\nfiles = ["services/api/service.py", "services/web/a.py"]\n')

    assert _move(monkeypatch, tmp_path, "api", "--repo", "acme") == 0

    assert (artifacts / "services/acme/api/ops/stack.toml").read_text() == 'book = "services.acme.api"\n'
    assert (artifacts / "services/acme/api/ops/templates/a.j2").read_text() == "{{ services.acme.api }}\n"
    assert (artifacts / "services/web/stack.yml").read_text() == "owner: services.acme.api\npath: services/api/x\n"
    assert (artifacts / "services/web/stack.yaml").read_text() == "owner: services.acme.api\n"
    assert (artifacts / ".agent-checks.toml").read_text() == (
        'book = "services.acme.api"\nfiles = ["services/acme/api/service.py", "services/web/a.py"]\n'
    )
    assert "rewrote 2 reference(s) in .agent-checks.toml" in capsys.readouterr().out


def test_a_dry_run_says_what_would_change_and_changes_nothing(tmp_path, monkeypatch, capsys):
    artifacts = _artifacts()
    _flat(artifacts, "api", **{"index.tsv": "services.api.endpoints:Ping\tendpoint\tPing\n", "note.md": "see services/api/x.py\n"})
    write(artifacts / "services/web/foreign.py", 'Foreign("x", owner="services.api")\n')
    before = _tree(artifacts)

    assert _move(monkeypatch, tmp_path, "api", "--repo", "acme", "--dry-run") == 0

    out = capsys.readouterr().out
    assert _tree(artifacts) == before
    assert "would move services/api to services/acme/api" in out
    assert "would rewrite 1 reference(s) in services/web/foreign.py" in out
    assert "index.tsv" not in out
    assert "check by hand: services/acme/api/note.md:1: see services/api/x.py" in out


@pytest.mark.parametrize(
    ("arguments", "said"),
    [
        (["api"], "name the repository with --repo"),
        (["api", "--repo", "a.b"], "--repo"),
        (["api", "--repo", "a/b"], "--repo"),
        ([], "name the books to move"),
        (["gone", "--repo", "acme"], "services/gone"),
    ],
)
def test_a_move_that_cannot_be_judged_exits_2_and_says_why(tmp_path, monkeypatch, capsys, arguments, said):
    artifacts = _artifacts()
    _flat(artifacts, "api")
    before = _tree(artifacts)

    assert _move(monkeypatch, artifacts, *(arguments or ["--repo", "acme"])) == 2

    assert said in capsys.readouterr().err
    assert _tree(artifacts) == before
