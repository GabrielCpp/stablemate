"""Integrity tests for the frozen `seat-booking` app.

The app is what standalone QA is *scored against*, so a defect in it is worse than a
defect in the harness: the harness fails loudly, the fixture just moves the number. These
tests cover the three ways it can rot silently.

* **The book stops being clean.** A fixture with an `unparsed-check` in it hands the run
  under measurement a broken obligation and then counts the resulting miss against QA.
* **A story's manifest stops matching the tree.** `diff.yml` is what materialization reads;
  a path renamed in the app and not in the manifest produces a trial whose diff is not the
  story's, which is invisible in the score and fatal to it.
* **Materialization stops producing a worktree diff.** QA mints obligations from
  uncommitted changes; a trial that commits everything obligates nothing and every run
  passes. That failure mode reads exactly like "QA found no problems".

No docker and no agent here — this is the app and the manifest logic, nothing that costs
money to check.
"""

from __future__ import annotations

import contextlib
import difflib
import importlib.util
import re
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
from paddock.registry import REGISTRY
import yaml

DATA = Path(__file__).parents[1]
APP = DATA / "apps" / "seat-booking"

@contextlib.contextmanager
def _tasks_dir_on_path() -> Iterator[None]:
    """Stand in for the interpreter, exactly as `paddock.loader` does when it loads a task."""
    saved = sys.path[:]
    sys.path.insert(0, str(DATA / "tasks"))
    try:
        yield
    finally:
        sys.path[:] = saved


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None  # noqa: S101 - a real file on disk
    module = importlib.util.module_from_spec(spec)
    # The registry is module-global and a task module declares into it at import: reset it
    # around the load, exactly as `paddock.loader` does, or the second task loaded in this
    # process refuses on a name the first one claimed.
    REGISTRY.reset()
    with _tasks_dir_on_path():
        sys.modules[name] = module
        spec.loader.exec_module(module)
    REGISTRY.reset()
    return module


# `_stablemate` first: the modules below import it by name, and a second instance loaded
# afterwards would shadow it — leaving this file's `sm.TrialError` a different class from
# the one the code under test raises, and every `pytest.raises` on it a false negative.
sm = _load("_stablemate", DATA / "tasks" / "_stablemate.py")
fx = _load("_forensics", DATA / "tasks" / "_forensics.py")
frozen = _load("_frozenapp", DATA / "tasks" / "_frozenapp.py")
TASK = _load("_task_under_test", DATA / "tasks" / "seat_booking_qa.py")

STORIES = ("seat-map", "seat-hold", "confirm-booking")

# The widest defect in the key removes a nine-line docstring paragraph along with the two
# lines of code it described — a variant that leaves the prose in place documents the bug it
# plants. Well clear of that, and an order of magnitude under a whole-file copy.
MAX_DEFECT_DIFF_LINES = 24


def manifest(story: str) -> dict[str, list[str]]:
    data = yaml.safe_load((APP / "stories" / story / "diff.yml").read_text(encoding="utf-8"))
    return {"changed": list(data.get("changed") or []), "added": list(data.get("added") or [])}


# ── the book ──────────────────────────────────────────────────────────────────────────


def test_doctor_is_clean() -> None:
    """0 errors and 0 warnings, which is the bar the app was authored to.

    Warnings count here where they would not in a working repo: `undeclared-obligation` and
    `compound-normative-bullet` are both warnings, and both describe a book that cannot be
    used as an answer key — the first leaves a bullet nothing has to verify, the second a
    bullet two different verdicts can both honestly claim.
    """
    from ostler.api import Ostler  # noqa: PLC0415 - a heavy import only this test needs

    report = Ostler(APP).doctor().data
    assert report["errors"] == 0, report["findings"]
    assert report["warnings"] == 0, report["findings"]


def test_the_book_is_already_canonical() -> None:
    """`ostler fmt` must have nothing to say about the fixture, or the score is unreadable.

    A trial's QA lane edits the book, and the diff between the authored book and the one the
    trial ends with is the evidence for whether the obligations moved while they were being
    measured. A non-canonical fixture makes that diff useless: the run converges on the
    canonical shape on its way past, and 3 lines of real change arrive inside 89 lines of
    bullet reordering. This was not hypothetical — it is what the first scored round did.
    """
    from ostler.api import Ostler  # noqa: PLC0415 - a heavy import only this test needs

    unformatted = Ostler(APP).fmt(check=True)
    assert not unformatted, f"run `ostler fmt` in {APP}: {unformatted}"


def test_every_screen_selector_is_one_the_render_scan_can_address() -> None:
    """A documented selector must be a form `ostler vet` can resolve, or the node reads missing.

    The scan mints `#id` or `tag.class:nth(i)` for each element it measures, and vet matches a
    documented selector against those strings — with one extra vocabulary, `tag[role="..."]`,
    resolved against the role the scan recorded. Any other attribute predicate matches nothing,
    however faithfully it describes the DOM: `section[aria-label="Seat map"]` addressed exactly
    the right element and vet reported it `missing` on a clean render, which put a standing
    failure in every control and made the one defect that moves that region unmeasurable —
    a misplacement cannot be seen on an element vet never finds.
    """
    screens = sorted((APP / "docs" / "features").rglob("gui/screens/*.md"))
    assert screens, "the fixture documents no screens"
    addressable = re.compile(
        r"""^(?:\#[\w-]+|[a-zA-Z][\w-]*(?:\.[\w-]+)*(?:\[role=["'][\w-]+["']\])?)$"""
    )
    for screen in screens:
        for line in screen.read_text(encoding="utf-8").splitlines():
            if not line.startswith("- selector:"):
                continue
            selector = line.split(":", 1)[1].strip().strip("`")
            assert addressable.match(selector), (
                f"{screen.name}: `{selector}` is a form the render scan never mints — "
                "address the element by id, by tag and class, or by its ARIA role"
            )


def test_the_fixture_ships_the_stories_it_claims() -> None:
    from ostler.api import Ostler  # noqa: PLC0415

    okf = Ostler(APP)
    slugs = {node.get("slug") or node.get("name") for node in okf.list("story")}
    assert set(STORIES) <= slugs


# ── the manifests ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("story", STORIES)
def test_every_manifest_path_exists_in_the_app(story: str) -> None:
    diff = manifest(story)
    for rel in [*diff["changed"], *diff["added"]]:
        assert (APP / rel).is_file(), f"{story}: {rel} is in diff.yml but not in the app tree"


@pytest.mark.parametrize("story", STORIES)
def test_changed_paths_have_a_pre_image_and_added_paths_do_not(story: str) -> None:
    """The asymmetry is the whole manifest contract.

    A `changed:` path with no `pre/` would be committed at its finished content and
    disappear from the story's diff; an `added:` path *with* one would be committed at all,
    which is the opposite of added. Both produce a trial that runs and reports a number.
    """
    diff = manifest(story)
    for rel in diff["changed"]:
        assert (APP / "stories" / story / "pre" / rel).is_file(), f"{story}: no pre/ for {rel}"
    for rel in diff["added"]:
        assert not (APP / "stories" / story / "pre" / rel).exists(), (
            f"{story}: {rel} is added but has a pre/ image"
        )


@pytest.mark.parametrize("story", STORIES)
def test_no_image_names_a_path_the_manifest_does_not(story: str) -> None:
    """A stale `pre/` or `post/` file is dead weight that reads as coverage."""
    diff = manifest(story)
    declared = {*diff["changed"], *diff["added"]}
    for phase in ("pre", "post"):
        root = APP / "stories" / story / phase
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                rel = path.relative_to(root).as_posix()
                assert rel in declared, f"{story}: {phase}/{rel} is not in diff.yml"


def test_each_story_starts_where_the_previous_one_ended() -> None:
    """Story N's `pre/` image is story N-1's `post/` image, byte for byte.

    Without this the stories are three unrelated snapshots rather than one history, and a
    trial on story 3 can present code story 2's trial never contained — so the same defect
    scores differently depending on which story it was seeded in.
    """
    for earlier, later in zip(STORIES, STORIES[1:], strict=False):
        for rel in manifest(later)["changed"]:
            after = frozen.story_image(APP, earlier, rel, phase="post")
            before = APP / "stories" / later / "pre" / rel
            assert before.read_bytes() == after.read_bytes(), (
                f"{later}/pre/{rel} is not {earlier}'s post-image"
            )


# ── materialization ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("story", STORIES)
def test_materialize_leaves_exactly_this_story_uncommitted(story: str, tmp_path: Path) -> None:
    dest = frozen.materialize(APP, story, tmp_path / "seat-booking")
    diff = manifest(story)

    porcelain = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=dest, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    dirty = {line[3:]: line[:2].strip() for line in porcelain}

    assert set(dirty) == {*diff["changed"], *diff["added"]}
    for rel in diff["changed"]:
        assert dirty[rel] == "M"
    for rel in diff["added"]:
        assert dirty[rel] == "??"


@pytest.mark.parametrize("story", STORIES)
def test_materialize_puts_this_story_content_in_the_worktree(story: str, tmp_path: Path) -> None:
    """The worktree holds the story's *post* image — the app tree only for the last story."""
    dest = frozen.materialize(APP, story, tmp_path / "seat-booking")
    diff = manifest(story)
    for rel in [*diff["changed"], *diff["added"]]:
        expected = frozen.story_image(APP, story, rel, phase="post").read_bytes()
        assert (dest / rel).read_bytes() == expected


def test_materialize_does_not_ship_the_answer_key(tmp_path: Path) -> None:
    """The seeded-defect list and the pre-images must not reach the tree QA reads.

    An agent that can read `defects.yml` is not being measured on detection, and nothing in
    its output would say so.
    """
    dest = frozen.materialize(APP, "seat-hold", tmp_path / "seat-booking")
    for name in frozen.NOT_THE_APP:
        assert not (dest / name).exists(), f"{name} was copied into the trial tree"


@pytest.mark.parametrize("story", STORIES)
def test_materialize_keeps_every_authored_story(story: str, tmp_path: Path) -> None:
    """The epic and all three story.md files reach the trial.

    Not a restatement of the copy: the exclusion above is by name, and `stories` is also
    what an epic calls its story folders. Excluding it at any depth deletes every
    `story.md`, and the run refuses to plan against an unauthored story — a failure that
    looks like a workflow bug and is a fixture bug.
    """
    dest = frozen.materialize(APP, "seat-hold", tmp_path / "seat-booking")
    epic = dest / "docs" / "epics" / "0001-seat-booking"
    assert (epic / "epic.md").is_file()
    assert (epic / "stories" / story / "story.md").is_file()


def test_materialized_book_is_unchanged(tmp_path: Path) -> None:
    """The book sits at its authored state on both sides of HEAD.

    A trial whose book is also uncommitted would let QA read the obligations as part of the
    work under review, which is the situation the OKF context is built to avoid.
    """
    dest = frozen.materialize(APP, "confirm-booking", tmp_path / "seat-booking")
    changed_docs = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", "docs"],
        cwd=dest, capture_output=True, text=True, check=True,
    ).stdout
    assert changed_docs == ""


@pytest.mark.parametrize("story", STORIES)
def test_the_obligation_packet_builds_clean_on_a_trial(story: str, tmp_path: Path) -> None:
    """Every story's QA context builds with no error-severity health finding.

    This is what a trial does first, and an `unmapped-change` there is not a warning the run
    walks past: the QA lane sends the packet to a repair agent, which edits the frozen book
    before a scenario runs. The control then measures a fixture nobody authored, and the
    minutes and tokens the repair spent land in the score as QA's. It only reproduces on a
    materialized worktree — `doctor` is clean either way, because the finding is about the
    story's diff and not about the book on its own — which is why it is checked here rather
    than left to the round to discover.
    """
    from ostler.api import Ostler  # noqa: PLC0415 - a heavy import only this test needs

    dest = frozen.materialize(APP, story, tmp_path / "seat-booking")
    outcome = Ostler(dest).qa_context(base="HEAD", spec=dest / "docs" / "specs" / story)
    errors = [
        finding for finding in outcome.data.get("healthFindings", [])
        if finding.get("severity") == "error"
    ]
    assert not errors, errors
    assert outcome.ok, outcome.data.get("status")


# ── the answer key ────────────────────────────────────────────────────────────────────


def defects() -> list[dict[str, str]]:
    data = yaml.safe_load((APP / "defects.yml").read_text(encoding="utf-8"))
    return list(data["defects"])


def defect_ids() -> list[str]:
    return [row["id"] for row in defects()]


def obligation_ids() -> set[str]:
    """Every obligation id this book can mint, independent of any diff.

    `build_context` mints these against a `base..head` diff, which needs a git repo and takes
    the better part of a minute. The private helpers underneath it are the same code path
    minus the diff — which is what a check on the answer key wants, since a defect's row must
    resolve whichever story it is seeded in.
    """
    from ostler.model import load  # noqa: PLC0415 - a heavy import only these tests need
    from ostler.qa.context import _obligations, _serialized_graph  # noqa: PLC0415

    nodes, _edges, _ends, _scopes, _details = _serialized_graph(load(APP))
    return {
        obligation["id"]
        for node in nodes.values()
        for obligation in _obligations(
            node, [], journey=str(node.get("type", "")) in ("flow", "journey")
        )
    }


def test_the_answer_key_names_its_defects_once() -> None:
    ids = defect_ids()
    assert len(ids) == len(set(ids)), ids
    assert set(ids) == {path.name for path in (APP / "defects").iterdir() if path.is_dir()}


@pytest.mark.parametrize("row", defects(), ids=defect_ids())
def test_every_defect_variant_exists_on_both_sides(row: dict[str, str]) -> None:
    """A row names a file that exists as a variant *and* in the app.

    Only the pair is meaningful: a variant with no counterpart in the app tree overwrites
    nothing the story implements, and an app path with no variant is a row that applies
    nothing at all. Either way the trial runs and reports a catch it never earned.
    """
    assert (APP / "defects" / row["id"] / row["path"]).is_file()
    assert (APP / row["path"]).is_file()


@pytest.mark.parametrize("row", defects(), ids=defect_ids())
def test_every_defect_obligation_resolves(row: dict[str, str]) -> None:
    """An id the book no longer mints is a row that can only ever be scored as missed."""
    assert row["obligation"] in obligation_ids(), row["obligation"]


@pytest.mark.parametrize("row", defects(), ids=defect_ids())
def test_every_defect_actually_changes_the_story_image(row: dict[str, str]) -> None:
    """The variant must differ from what the story would otherwise ship — and only there."""
    correct = frozen.story_image(APP, row["story"], row["path"], phase="post").read_bytes()
    assert (APP / "defects" / row["id"] / row["path"]).read_bytes() != correct


@pytest.mark.parametrize("row", defects(), ids=defect_ids())
def test_every_defect_variant_is_the_story_image_plus_one_localized_edit(
    row: dict[str, str],
) -> None:
    """A variant is the story's own file with a small mutation in it — nothing else.

    The failure this catches is drift, not authorship: a payload is a whole copy of a file
    the app still edits afterwards, so a later refactor of that file leaves the copy behind.
    Seeding it then reverts the refactor *and* plants the defect, and the trial carries a
    mutation far larger than the answer key describes — which destroys the localization the
    key depends on and makes the resulting catch or miss say nothing about QA. It is
    invisible to every other test here: the payload still differs from the image, still
    compiles, still lands inside the story's diff.
    """
    correct = frozen.story_image(APP, row["story"], row["path"], phase="post").read_text(
        encoding="utf-8"
    )
    variant = (APP / "defects" / row["id"] / row["path"]).read_text(encoding="utf-8")
    changed = [
        line
        for line in difflib.unified_diff(
            correct.splitlines(), variant.splitlines(), n=0, lineterm=""
        )
        if line[:1] in {"+", "-"} and not line.startswith(("+++", "---"))
    ]
    assert len(changed) <= MAX_DEFECT_DIFF_LINES, (
        f"{row['id']}: {len(changed)} changed lines in {row['path']} — a payload this large "
        "is a stale copy of the file, not a seeded defect"
    )


@pytest.mark.parametrize("row", defects(), ids=defect_ids())
def test_every_defect_variant_is_importable(row: dict[str, str]) -> None:
    """A variant that will not compile is caught by anything and measures nothing."""
    source = (APP / "defects" / row["id"] / row["path"]).read_text(encoding="utf-8")
    compile(source, f"{row['id']}/{row['path']}", "exec")


@pytest.mark.parametrize("row", defects(), ids=defect_ids())
def test_every_defect_declares_a_route_and_an_expectation(row: dict[str, str]) -> None:
    assert row["expect"] == "contradicted"
    assert row["caught_by"] in {"run", "audit"}
    assert row["why"].strip()


# ── scoring ───────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("row", defects(), ids=defect_ids())
def test_seeding_a_defect_stays_inside_the_story_diff(row: dict[str, str], tmp_path: Path) -> None:
    """Planting the defect changes the seeded file and leaves the rest of the trial alone.

    Both halves matter. A variant that lands somewhere else is a second, undocumented defect
    the answer key does not name — and a trial carrying two defects scores one of them as a
    catch whichever one QA found.
    """
    def tree(root: Path) -> dict[Path, bytes]:
        return {
            path: path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file() and ".git" not in path.relative_to(root).parts
        }

    dest = frozen.materialize(APP, row["story"], tmp_path / "seat-booking")
    before = tree(dest)
    frozen.seed_defect(APP, row, dest)
    after = tree(dest)

    assert set(after) == set(before)
    assert [p for p in after if after[p] != before[p]] == [dest / row["path"]]
    assert (dest / row["path"]).read_bytes() == (
        APP / "defects" / row["id"] / row["path"]
    ).read_bytes()


def test_selecting_defects_defaults_to_the_whole_key() -> None:
    assert [row["id"] for row in frozen.select_defects(APP, [])] == defect_ids()
    assert [row["id"] for row in frozen.select_defects(APP, ["D3", "D1"])] == ["D3", "D1"]
    # A bad `--param defects=` is a task error naming the key, not a bare process exit:
    # the round is driven by paddock now, and an exit code says nothing to the score.
    with pytest.raises(sm.TrialError, match="no such defect"):
        frozen.select_defects(APP, ["D99"])


def test_a_contradicted_obligation_is_a_catch() -> None:
    row = {"id": "D1", "obligation": "okf:a#b:contract", "expect": "contradicted"}
    verdict, _ = frozen.classify(row, {"okf:a#b:contract": "contradicted"}, {"verdict": "stands"})
    assert verdict == "caught"


def test_an_audit_refutation_naming_the_obligation_is_a_catch() -> None:
    """The second route exists because which one fires is the plan's choice, not QA's bar."""
    row = {
        "id": "D9", "obligation": "okf:a#b:contract", "expect": "contradicted", "caught_by": "audit"
    }
    audit = {"verdict": "refuted", "findings": [{"target": "okf:a#b:contract", "issue": "…"}]}
    verdict, because = frozen.classify(row, {"okf:a#b:contract": "covered"}, audit)
    assert (verdict, because) == ("caught", "audit refutation")


def test_a_covered_obligation_over_a_seeded_defect_is_a_miss() -> None:
    row = {"id": "D1", "obligation": "okf:a#b:contract", "expect": "contradicted"}
    verdict, _ = frozen.classify(row, {"okf:a#b:contract": "covered"}, {"verdict": "stands"})
    assert verdict == "missed"


def test_an_audit_row_is_inconclusive_when_the_configuration_gave_the_auditor_no_turn() -> None:
    """A first-verdict trial never enters `audit`, so a row only the auditor can see is a
    question this configuration did not ask — scoring it `missed` would grade the absence of
    a lane, not the plan. A run row in the same trial is still a miss: its route did run."""
    audit_row = {
        "id": "D9", "obligation": "okf:a#b:contract", "expect": "contradicted", "caught_by": "audit"
    }
    assert frozen.classify(audit_row, {"okf:a#b:contract": "covered"}, {}, audit_ran=False) == (
        "inconclusive", "no audit turn in this configuration"
    )
    assert frozen.classify(audit_row, {"okf:a#b:contract": "covered"}, {}, audit_ran=True) == (
        "missed", "covered"
    )
    run_row = {**audit_row, "caught_by": "run"}
    assert frozen.classify(run_row, {"okf:a#b:contract": "covered"}, {}, audit_ran=False) == (
        "missed", "covered"
    )


def test_a_catch_by_the_other_route_is_still_a_catch_and_says_so() -> None:
    """Which route fires is the plan's choice, so the verdict is `caught` either way — but
    the surprise is written next to it, in the column a reader already has open."""
    audit_row = {
        "id": "D9", "obligation": "okf:a#b:contract", "expect": "contradicted", "caught_by": "audit"
    }
    assert frozen.classify(audit_row, {"okf:a#b:contract": "contradicted"}, {}) == (
        "caught", "contradicted (expected audit)"
    )
    assert frozen.classify(
        audit_row, {"okf:a#b:contract": "covered"}, {}, survived=False
    ) == ("caught", "defect repaired (expected audit)")
    run_row = {**audit_row, "caught_by": "run"}
    refutation = {"verdict": "refuted", "findings": [{"target": "okf:a#b:contract"}]}
    assert frozen.classify(run_row, {"okf:a#b:contract": "covered"}, refutation) == (
        "caught", "audit refutation (expected run)"
    )


def test_a_row_with_an_unknown_route_is_refused_at_load(tmp_path: Path) -> None:
    app = tmp_path / "app"
    app.mkdir()
    (app / "defects.yml").write_text(
        "defects:\n  - id: X1\n    story: s\n    path: a.py\n    obligation: okf:a#b:c\n"
        "    expect: contradicted\n    caught_by: reviewer\n",
        encoding="utf-8",
    )
    with pytest.raises(frozen.TrialError, match="caught_by: 'reviewer'"):
        frozen.load_defects(app)
    (app / "defects.yml").write_text(
        "defects:\n  - id: X1\n    story: s\n    path: a.py\n    obligation: okf:a#b:c\n"
        "    expect: contradicted\n",
        encoding="utf-8",
    )
    assert frozen.load_defects(app)[0]["caught_by"] == "run"


def test_a_repaired_defect_is_a_catch_even_though_the_map_reads_covered() -> None:
    """The loudest detection there is: QA saw it, triaged it `code`, and fixed the product.

    The terminal evidence map is then computed over a repaired app and correctly reports
    `covered`, so end-state-only scoring calls the best outcome a miss.
    """
    row = {"id": "D1", "obligation": "okf:a#b:contract", "expect": "contradicted"}
    verdict, because = frozen.classify(
        row, {"okf:a#b:contract": "covered"}, {"verdict": "stands"}, survived=False
    )
    assert (verdict, because) == ("caught", "defect repaired")


def test_the_seeded_file_is_the_witness_that_the_defect_survived(tmp_path: Path) -> None:
    row = frozen.select_defects(APP, ["D1"])[0]
    target = tmp_path / row["path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(APP / "defects" / row["id"] / row["path"], target)
    assert frozen.defect_survived(APP, row, tmp_path) is True

    target.write_text(target.read_text(encoding="utf-8") + "\n# repaired\n", encoding="utf-8")
    assert frozen.defect_survived(APP, row, tmp_path) is False


@pytest.mark.parametrize(
    ("statuses", "because"),
    [
        (None, "no evidence map"),
        ({}, "obligation not owed by this trial"),
        ({"okf:a#b:contract": "uncovered"}, "uncovered"),
    ],
)
def test_a_harness_failure_is_never_scored_as_detection(
    statuses: dict[str, str] | None, because: str
) -> None:
    """`uncovered` is not a catch: nothing was asserted, so nothing was detected."""
    row = {"id": "D1", "obligation": "okf:a#b:contract", "expect": "contradicted"}
    assert frozen.classify(row, statuses, {}) == ("inconclusive", because)


def test_an_unbilled_round_is_priced_from_tokens_and_marked_as_an_estimate() -> None:
    """opencode reports a literal `$0` over millions of tokens. Printing `$0.00` there
    says the round was free and kills the whole column on the mandated backend."""
    assert fx.money([{"cost_usd": 0.94, "est_cost_usd": 0.71}]) == "$0.94"
    assert fx.money([{"cost_usd": 0.0, "est_cost_usd": 0.71}]) == "~$0.71"
    # Neither a bill nor a rate for the model: unpriced, and a zero would be a claim.
    assert fx.money([{"cost_usd": 0.0, "est_cost_usd": None}]) == "$?"


def test_the_clean_control_scores_false_on_any_contradiction() -> None:
    assert frozen.classify(None, {"okf:a#b:contract": "covered"}, {"verdict": "stands"})[0] == "clean"
    assert frozen.classify(None, {"okf:a#b:contract": "contradicted"}, {})[0] == "false"
    assert frozen.classify(None, {"okf:a#b:contract": "covered"}, {"verdict": "refuted"})[0] == "false"


def test_the_task_points_at_the_app_and_names_the_trial_dir() -> None:
    """The declaration is now the task module's `FIXTURE`, not a `fixtures/*.yml` entry.

    Story order is no longer part of it: a round enumerates its stories from the answer key
    rather than from a hand-written list, so the fixture has no order to get wrong. What it
    still has to get right is the two paths.
    """
    assert DATA / TASK.FIXTURE.app == APP
    # farrier derives generated skill names from the basename; anything else dangles.
    assert TASK.FIXTURE.repo_dir == "seat-booking"
    assert {row["story"] for row in defects()} <= set(STORIES)


def test_the_audit_task_is_the_qa_round_with_the_auditor_turned_on() -> None:
    """`seat-booking-audit` exists to score the one row a first-verdict round cannot: it
    must run audit-on, be scoped to exactly the rows filed `caught_by: audit`, and share
    the QA task's app and repo_dir so the two labels stay comparable row-for-row."""
    audit = _load("_seat_booking_audit_task", DATA / "tasks" / "seat_booking_audit.py")
    assert audit.FIXTURE.first_verdict is False
    assert audit.FIXTURE.app == TASK.FIXTURE.app
    assert audit.FIXTURE.repo_dir == TASK.FIXTURE.repo_dir
    assert audit.FIXTURE.leverage == TASK.FIXTURE.leverage
    audit_rows = {row["id"] for row in defects() if row["caught_by"] == "audit"}
    assert set(audit.FIXTURE.defects) == audit_rows == {"D9"}
