"""The installed-skill guard (`prepare._references_ok`) against farrier's layout.

Farrier installs a skill under the consuming repo's prefix — `ostler-okf` lands as
`<repo>-ostler-okf` — and the first prefixed repo showed what the old exact-name
lookup did with that: refused every run on a repo whose skill was present and
complete. Both spellings are therefore pinned here, along with the two refusals the
guard exists for (no install at all, an install that predates the references corpus).
"""
from __future__ import annotations

from pathlib import Path

from workhorse_workflows.okf_builder.main.nodes.prepare import _references_ok


def _install(root: Path, name: str, *, complete: bool = True) -> None:
    skill = root / ".claude/skills" / name
    (skill / "references/node-types").mkdir(parents=True)
    if complete:
        (skill / "references/bullet-grammar.md").write_text("#\n", encoding="utf-8")
        (skill / "references/check-vocabulary.md").write_text("#\n", encoding="utf-8")


def test_accepts_the_bare_install_name(tmp_path: Path) -> None:
    _install(tmp_path, "ostler-okf")
    ok, why = _references_ok(tmp_path)
    assert ok, why


def test_accepts_the_repo_prefixed_install_name(tmp_path: Path) -> None:
    _install(tmp_path, "acme-ostler-okf")
    ok, why = _references_ok(tmp_path)
    assert ok, why


def test_refuses_a_repo_with_no_install(tmp_path: Path) -> None:
    ok, why = _references_ok(tmp_path)
    assert not ok
    assert "no installed ostler-okf skill" in why


def test_refuses_a_prefixed_install_missing_the_corpus(tmp_path: Path) -> None:
    _install(tmp_path, "acme-ostler-okf", complete=False)
    ok, why = _references_ok(tmp_path)
    assert not ok
    assert "missing" in why
