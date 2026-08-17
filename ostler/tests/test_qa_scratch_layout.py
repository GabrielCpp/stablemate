"""Where a dry run's artifacts land, and what a caller is allowed to call one.

A repo ignores its QA evidence by naming the `qa` directory. The old layout put every
rehearsal in a *sibling* — `qa-dry-run/`, and, once agents and operators started inventing
their own, some forty roots per spec — so none of it was ignored and all of it shipped:
2,167 tracked files and 297 MB of traces and video in the repo that motivated this. These
cases pin the two halves of the fix: scratch nests inside `qa/`, and `--out-dir` is a name
rather than a path, so no caller can put it anywhere else.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ostler.qa.clean import cmd_clean, legacy_scratch_roots
from ostler.qa.session import (
    QA_DIRNAME,
    RESERVED_LABELS,
    ScratchLabelError,
    _resolve_out,
    scratch_dirname,
)


# ---------------------------------------------------------------------------
# the label
# ---------------------------------------------------------------------------


def test_a_label_resolves_inside_the_ignored_directory():
    """The whole point of the layout: one ignored subtree, no siblings to drift off."""
    assert scratch_dirname("copy-link") == f"{QA_DIRNAME}/copy-link"


@pytest.mark.parametrize(
    "label",
    [
        "../../etc",
        "qa-dry-run/copy-link",
        "docs/specs/story/qa-dry-run",
        "/absolute/path",
        ".",
        "..",
        "",
        "   ",
        r"windows\sep",
    ],
)
def test_a_path_is_not_a_label(label: str):
    """Traversal, an absolute path, and the repo-relative form are unrepresentable rather
    than validated against — the last one is what produced a committed
    `docs/specs/x/docs/specs/x/qa-operator-firefox/traces/*.zip`, because ostler joined a
    repo-relative `--out-dir` onto the spec directory."""
    with pytest.raises(ScratchLabelError):
        scratch_dirname(label)


@pytest.mark.parametrize("label", sorted(RESERVED_LABELS))
def test_a_directory_the_scored_run_owns_is_not_a_label(label: str):
    """`steps/`, `asserts/`, `traces/`, `videos/` and `screenshots/` are written by the
    scored run itself, so a dry run under one of those names would be indistinguishable
    from it. `qa` is refused for a different reason: it used to mean "the scored ledger",
    and reading it as a label would silently produce `qa/qa/`."""
    with pytest.raises(ScratchLabelError):
        scratch_dirname(label)


def test_the_refusal_says_how_to_ask_for_the_scored_ledger():
    """An agent that passes the old `--out-dir qa` has to be told the flag is now omitted,
    not merely that its argument was rejected."""
    with pytest.raises(ScratchLabelError, match="omitting the flag"):
        scratch_dirname(QA_DIRNAME)


# ---------------------------------------------------------------------------
# `out:` rewriting
# ---------------------------------------------------------------------------


def test_an_out_path_follows_the_run_into_its_nested_directory(tmp_path: Path):
    """A plan writes `out: qa/steps/body.json` meaning "this run's ledger", and a dry run
    has to honour the meaning. Rewriting with the directory's *name* was right only while
    scratch was a direct child of the spec: under `qa/<label>/` the name is `<label>`, so
    the step would land in `<spec>/<label>/` — a stray sibling outside the ignore, which is
    the exact escape the layout exists to close."""
    spec = tmp_path / "docs" / "specs" / "story"
    qa_dir = spec / scratch_dirname("copy-link")
    qa_dir.mkdir(parents=True)

    resolved = _resolve_out("qa/steps/body.json", spec, qa_dir)

    assert resolved == (qa_dir / "steps" / "body.json").resolve()


def test_a_scored_out_path_still_lands_in_the_ledger(tmp_path: Path):
    spec = tmp_path / "docs" / "specs" / "story"
    qa_dir = spec / QA_DIRNAME
    qa_dir.mkdir(parents=True)

    assert _resolve_out("qa/steps/body.json", spec, qa_dir) == (
        spec / "qa" / "steps" / "body.json"
    ).resolve()


def test_a_relative_spec_directory_does_not_double_the_path(tmp_path: Path, monkeypatch):
    """`qa_dir` is `spec_dir / qa_dirname`, so substituting it whole into a relative path
    would re-anchor it against the spec a second time — `docs/specs/x/docs/specs/x/qa/…`,
    the committed doubling this plan started from, reintroduced from the other side."""
    monkeypatch.chdir(tmp_path)
    spec = Path("docs/specs/story")
    qa_dir = spec / scratch_dirname("copy-link")
    qa_dir.mkdir(parents=True)

    assert _resolve_out("qa/steps/body.json", spec, qa_dir) == (
        tmp_path / "docs/specs/story/qa/copy-link/steps/body.json"
    )


def test_an_out_path_may_still_not_escape_the_spec(tmp_path: Path):
    spec = tmp_path / "docs" / "specs" / "story"
    qa_dir = spec / QA_DIRNAME
    qa_dir.mkdir(parents=True)

    with pytest.raises(ValueError, match="escapes spec directory"):
        _resolve_out("../../../etc/passwd", spec, qa_dir)


# ---------------------------------------------------------------------------
# `ostler qa clean`
# ---------------------------------------------------------------------------


def _legacy(spec: Path, name: str, size: int = 32) -> Path:
    root = spec / name
    (root / "traces").mkdir(parents=True)
    (root / "traces" / "run.zip").write_bytes(b"x" * size)
    return root


def test_clean_finds_every_family_of_legacy_root(tmp_path: Path):
    """The four the client repo grew: the sanctioned dry-run root, the fix flow's, the
    hand-driven operator sessions', and a sandbox."""
    spec = tmp_path / "docs" / "specs" / "story"
    spec.mkdir(parents=True)
    for name in ("qa-dry-run", "qa-fix-1", "qa-operator-firefox", "qa-sandbox"):
        _legacy(spec, name)

    found = {path.name for path in legacy_scratch_roots(tmp_path)}

    assert found == {"qa-dry-run", "qa-fix-1", "qa-operator-firefox", "qa-sandbox"}


def test_clean_never_touches_the_ledger_or_the_plan_fixtures(tmp_path: Path):
    """`qa-inputs/` holds a plan's `inputs:` — tracked on purpose, resolved as
    `spec_dir / path`, and indistinguishable from scratch by prefix alone. It is the reason
    this is an explicit command rather than a wider sweep inside `clear_qa_evidence`."""
    spec = tmp_path / "docs" / "specs" / "story"
    (spec / "qa-inputs").mkdir(parents=True)
    (spec / "qa-inputs" / "seed.json").write_text("{}", encoding="utf-8")
    (spec / "qa" / "copy-link").mkdir(parents=True)
    (spec / "qa" / "qa-run.ndjson").write_text("", encoding="utf-8")

    assert legacy_scratch_roots(tmp_path) == []

    outcome = cmd_clean(tmp_path, apply=True)

    assert outcome.ok, outcome.message
    assert (spec / "qa-inputs" / "seed.json").is_file()
    assert (spec / "qa" / "qa-run.ndjson").is_file()


def test_clean_lists_and_deletes_nothing_until_told(tmp_path: Path):
    """Deleting is irreversible and the caller is often an agent, so the default reports
    what it would remove and leaves it standing."""
    spec = tmp_path / "docs" / "specs" / "story"
    spec.mkdir(parents=True)
    root = _legacy(spec, "qa-operator-firefox")

    listed = cmd_clean(tmp_path, apply=False)

    assert listed.ok
    assert listed.data["removed"] is False
    assert [row["path"] for row in listed.data["roots"]] == [str(root)]
    assert listed.data["roots"][0]["files"] == 1
    assert "--yes" in listed.message
    assert root.is_dir()

    removed = cmd_clean(tmp_path, apply=True)

    assert removed.ok and removed.data["removed"] is True
    assert not root.exists()


def test_clean_on_a_clean_tree_is_success_not_a_finding(tmp_path: Path):
    outcome = cmd_clean(tmp_path, apply=True)
    assert outcome.ok
    assert outcome.data["roots"] == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
