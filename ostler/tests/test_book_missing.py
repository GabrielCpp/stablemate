"""`ostler book missing`: the tracked source files of an app that no element of the book names."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from ostler.book import App
from ostler.book.cli import cmd_missing
from ostler.book.service import Service


def _git(folder: Path, *arguments: str) -> None:
    subprocess.run(["git", "-C", str(folder), "-c", "user.name=t", "-c", "user.email=t@example.com", *arguments],
                   check=True, capture_output=True)


@pytest.fixture
def app(tmp_path: Path) -> Path:
    root = tmp_path / "web-app"
    for name in ("web/routes/home.tsx", "web/routes/about.tsx", "web/routes/home.test.tsx", "web/styles/site.css", "docs/guide.md"):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text("x\n")
    _git(tmp_path, "init", "--quiet", str(root))
    _git(root, "add", ".")
    _git(root, "commit", "--quiet", "-m", "init")
    return root


def _service(*source: str, roots: tuple[str, ...] = ("web",), ignore: tuple[str, ...] = (), declared: bool = True) -> Service[Any]:
    screen = SimpleNamespace(__name__="Home", source=source)
    book = App(roots=roots, verified="VERIFIED", ignore=ignore) if declared else None
    return cast("Service[Any]", SimpleNamespace(name="web", endpoints=(), records=(), screens=(screen,), interactions=(), app=book))


def _run(service: Service[Any], app: Path, *under: str, files: bool = False) -> int:
    return cmd_missing(service, argparse.Namespace(app=str(app), under=list(under), files=files))


def test_a_tracked_file_under_a_root_that_no_element_names_is_listed_and_exits_1(app, capsys):
    code = _run(_service("web/routes/home.tsx", ignore=("*.test.tsx", "*.css")), app)
    out = capsys.readouterr().out
    assert code == 1
    assert "- web/routes/about.tsx" in out
    assert "1 of 4 files are in no element and under no ignore pattern" in out
    assert "nothing missing" not in out


def test_a_file_an_element_names_is_not_listed(app, capsys):
    code = _run(_service("web/routes/home.tsx::Home", "web/routes/about.tsx", ignore=("*.test.tsx", "*.css")), app)
    out = capsys.readouterr().out
    assert code == 0
    assert "## Files no element names\n\n" in out
    assert out.rstrip().endswith("nothing missing")


def test_a_file_an_ignore_pattern_matches_is_not_listed_and_is_counted_under_the_pattern(app, capsys):
    _run(_service("web/routes/home.tsx", "web/routes/about.tsx", ignore=("*.test.tsx", "*.css")), app)
    out = capsys.readouterr().out
    assert "- web/routes/home.test.tsx" not in out
    assert "- *.test.tsx: 1 files" in out
    assert "- *.css: 1 files" in out


def test_under_widens_the_universe_past_the_roots(app, capsys):
    service = _service("web/routes/home.tsx", "web/routes/about.tsx", ignore=("*.test.tsx", "*.css"))
    assert _run(service, app) == 0
    capsys.readouterr()
    assert _run(service, app, "web", "docs") == 1
    assert "- docs/guide.md" in capsys.readouterr().out


def test_a_service_with_no_app_exits_2_and_says_how_to_declare_one(app, capsys):
    assert _run(_service(declared=False), app) == 2
    assert 'give Service app=App(roots=(...), verified="VERIFIED")' in capsys.readouterr().out


def test_a_folder_that_holds_no_tracked_file_exits_2_and_names_the_folder(app, capsys):
    assert _run(_service("web/routes/home.tsx"), app, "wbe") == 2
    out = capsys.readouterr().out
    assert "no tracked file under wbe" in out
    assert "nothing missing" not in out


def test_an_untracked_file_is_not_listed(app, capsys):
    (app / "web" / "routes" / "draft.tsx").write_text("x\n")
    _run(_service("web/routes/home.tsx", "web/routes/about.tsx", ignore=("*.test.tsx", "*.css")), app)
    assert "draft.tsx" not in capsys.readouterr().out


def test_a_named_file_is_mapped_to_the_elements_that_name_it_with_their_kind(app, capsys):
    service = _service("web/routes/home.tsx::Home", "web/routes/about.tsx", ignore=("*.test.tsx", "*.css"))
    _run(service, app)
    out = capsys.readouterr().out
    assert "## What the book names\n- web/routes/about.tsx: Home (screen)\n- web/routes/home.tsx: Home (screen)\n" in out
    assert out.index("## What the book names") < out.index("## Files no element names")


def test_files_lists_each_left_out_file_under_its_pattern_and_the_default_only_counts(app, capsys):
    service = _service("web/routes/home.tsx", "web/routes/about.tsx", ignore=("*.test.tsx", "*.css"))
    _run(service, app)
    assert "    web/routes/home.test.tsx" not in capsys.readouterr().out
    _run(service, app, files=True)
    assert "- *.test.tsx: 1 files\n    web/routes/home.test.tsx\n" in capsys.readouterr().out
