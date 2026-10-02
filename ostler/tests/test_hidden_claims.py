"""A claim a writer moved into an HTML comment is reported; a comment that holds no claim is not."""

from __future__ import annotations

from pathlib import Path

from ostler import doctor
from ostler.model import load

from conftest import write

_PAGE = "docs/features/acme/concepts/ledger.md"
_HEAD = "---\ntype: concept\ntitle: Ledger\n---\n# Ledger\n\n- code: `app.py`\n\n"


def _hidden(repo: Path, body: str) -> list[tuple[str, int | None]]:
    write(repo / _PAGE, _HEAD + body)
    write(repo / "app.py", "x = 1\n")
    return [(f.path, f.line) for f in doctor.run(load(repo)).findings if f.code == "hidden-claim"]


def test_a_comment_holding_a_claim_bullet_is_reported(repo: Path):
    body = "Entries are kept.\n\n<!--\n- rule: entries are append-only\n- emits: entry.recorded\n-->\n"

    assert _hidden(repo, body) == [(_PAGE, 11)]


def test_each_comment_holding_claims_is_reported_once(repo: Path):
    one = "<!--\n- rule: one\n- rule: two\n-->\n"

    assert len(_hidden(repo, f"{one}\nBetween.\n\n{one}")) == 2


def test_a_template_marker_is_not_a_claim(repo: Path):
    body = "<!-- ostler:template:ledger:start -->\n\nEntries are kept.\n\n<!-- ostler:template:ledger:end -->\n"

    assert _hidden(repo, body) == []


def test_a_note_in_a_comment_is_not_a_claim(repo: Path):
    body = "<!-- migrated from agents.yml's fixture block -->\n\n<!--\n- todo: revisit the wording\n-->\n"

    assert _hidden(repo, body) == []


def test_a_comment_inside_a_code_fence_is_not_a_claim(repo: Path):
    body = "```markdown\n<!--\n- rule: an example of a hidden claim\n-->\n```\n"

    assert _hidden(repo, body) == []
