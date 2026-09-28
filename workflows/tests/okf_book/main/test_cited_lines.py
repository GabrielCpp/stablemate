"""A citation costs the turn the part of the file it names: a declaration, a yaml key's block, or the whole file."""
from __future__ import annotations

from pathlib import Path

from workhorse_workflows.okf_book.main.nodes.cited_lines import CitedFiles, CitedLines, yaml_key_span
from workhorse_workflows.okf_book.shared.citations import Citation

OPENAPI = """openapi: 3.0.0
paths:
  /rows/{id}.json:
    get:
      summary: read a row

      responses:
        '200':
          description: ok
    delete:
      summary: drop a row
components:
  schemas:
    Row:
      type: object
"""

MODULE = "def first():\n    return 1\n\n\ndef second():\n    return 2\n"


def test_a_dotted_key_names_its_block_even_when_a_key_holds_a_dot() -> None:
    assert yaml_key_span(OPENAPI, "paths./rows/{id}.json.get") == (4, 9)
    assert yaml_key_span(OPENAPI, "paths./rows/{id}.json.delete") == (10, 11)
    assert yaml_key_span(OPENAPI, "components.schemas.Row") == (14, 15)


def test_a_dotted_key_no_block_holds_names_no_lines() -> None:
    assert yaml_key_span(OPENAPI, "paths./rows/{id}.json.put") is None
    assert yaml_key_span(OPENAPI, "info.title") is None


def test_a_citation_costs_the_declaration_it_names_or_the_whole_file_when_it_names_none_it_finds(tmp_path: Path) -> None:
    _ = (tmp_path / "app.py").write_text(MODULE, encoding="utf-8")
    files = CitedFiles(tmp_path)

    named = files.cited(Citation("app.py", None, "second"))
    unnamed = files.cited(Citation("app.py", None))
    missing = files.cited(Citation("app.py", None, "third"))

    assert named == CitedLines("app.py", (5, 6), 7)
    assert named is not None and named.label == "app.py:5-6"
    assert unnamed == missing == CitedLines("app.py", None, 14)
    assert files.cited(Citation("gone.py", None, "f")) is None
