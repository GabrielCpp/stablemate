"""`ostler book search` reads the books of the repository it is started in, and names a flat book's move."""

from __future__ import annotations

import os
import time
from pathlib import Path

from conftest import write
from test_book_home_resolution import _artifacts, _lone_repository, _ostler


def _book(root: Path, folder: str, term: str) -> None:
    write(root / folder / "service.py", "")
    index = root / folder / "index.tsv"
    write(index, f"endpoint\tThing\tendpoints.py:1\t{term} is here\n")
    later = time.time() + 5
    os.utime(index, (later, later))


def test_search_from_a_repository_reads_only_its_own_books(tmp_path):
    acme = _lone_repository(tmp_path)
    _book(_artifacts(), "services/acme/api", "ambrosia")
    _book(_artifacts(), "services/globex/api", "nectar")
    mine = _ostler(["book", "search", "ambrosia"], acme)
    assert mine.returncode == 0, mine.stdout + mine.stderr
    assert "services.acme.api" in mine.stdout
    other = _ostler(["book", "search", "nectar"], acme)
    assert other.returncode == 1, other.stdout + other.stderr
    assert "services.globex.api" not in other.stdout
    here = _ostler(["book", "search", "nectar"], _artifacts())
    assert here.returncode == 0, here.stdout + here.stderr
    assert "services.globex.api" in here.stdout
    both = _ostler(["book", "search", "ambrosia"], _artifacts())
    assert "services.acme.api" in both.stdout


def test_a_flat_book_in_the_artifacts_folder_is_named_with_the_move(tmp_path):
    acme = _lone_repository(tmp_path)
    _book(_artifacts(), "services/api", "ambrosia")
    done = _ostler(["book", "search", "ambrosia"], acme)
    assert "ostler book move api --repo acme" in done.stderr
    assert "services.api" not in done.stdout
    checked = _ostler(["book", "check", "services.acme.api", "--app", str(acme)], acme)
    assert checked.returncode != 0
    assert "ostler book move api --repo acme" in checked.stderr


def test_a_repository_named_like_a_service_is_not_taken_for_a_flat_book(tmp_path):
    acme = _lone_repository(tmp_path)
    _book(_artifacts(), "services/api/web", "ambrosia")
    done = _ostler(["book", "search", "ambrosia"], acme)
    assert "book move" not in done.stderr
