"""A skill declaring that one of its scripts must run at a git hook.

Farrier used to know one skill by name: the ostler staged-files gate was hardcoded, so
a second skill wanting a hook meant a second special case, and a repo selecting only
the first still carried the machinery for both. The declaration lives in the skill now,
which makes `farrier library --check` the place a broken one has to be caught — by
install time it is already shipped, and the shape farrier cannot read is exactly the
shape it reads as *no hooks*, which installs quietly and never runs.

    ./.venv/bin/python -m pytest tests/test_skill_hooks.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

from farrier.library_check import check_text
from farrier.skill_hooks import STAGES, SkillHook, hooks_for

FENCE = "---\nname: gate\ndescription: x\ntags: [cli]\n{hooks}---\n\n# Gate\n\nBody.\n"


def _skill(tmp_path: Path, hooks: str, *, ship_script: bool = True) -> Path:
    directory = tmp_path / "gate"
    directory.mkdir(exist_ok=True)
    if ship_script:
        scripts = directory / "scripts"
        scripts.mkdir(exist_ok=True)
        (scripts / "check.py").write_text("print('gate')\n", encoding="utf-8")
    path = directory / "SKILL.md"
    path.write_text(FENCE.format(hooks=hooks), encoding="utf-8")
    return path


def _codes(path: Path) -> list[str]:
    return [f.code for f in check_text(path.read_text(encoding="utf-8"), path)]


DECLARED = "hooks:\n  - stage: pre-commit\n    run: scripts/check.py\n"


# ---------------------------------------------------------------------------
# reading a declaration
# ---------------------------------------------------------------------------


def test_a_well_formed_declaration_passes_and_parses(tmp_path):
    path = _skill(tmp_path, DECLARED)

    assert _codes(path) == []
    assert hooks_for("demo-gate", {"hooks": [{"stage": "pre-commit", "run": "scripts/check.py"}]}) == [
        SkillHook(skill="demo-gate", stage="pre-commit", run="scripts/check.py")
    ]


def test_a_skill_declaring_nothing_declares_no_hooks(tmp_path):
    """The common case, and the one that must stay free: a bundled `scripts/` helper is
    something the *agent* runs, and installing it into every commit would be a surprise
    nobody asked for and nobody could see coming."""
    path = _skill(tmp_path, "")

    assert _codes(path) == []
    assert hooks_for("demo-gate", {}) == []


def test_install_never_raises_on_a_malformed_declaration(tmp_path):
    """A repo pinned to an older base library must keep installing; one bad key in a
    skill it does not even select cannot be what stops it. --check is the gate."""
    assert hooks_for("demo-gate", {"hooks": "scripts/check.py"}) == []
    assert hooks_for("demo-gate", {"hooks": [{"stage": "pre-push", "run": "x.py"}]}) == []


# ---------------------------------------------------------------------------
# what --check refuses
# ---------------------------------------------------------------------------


def test_a_run_naming_a_script_the_skill_does_not_ship(tmp_path):
    """The load-bearing one. It installs fine and fails at the moment somebody commits,
    which is the worst time to find out and the point farrier looks most like the
    culprit."""
    path = _skill(tmp_path, DECLARED, ship_script=False)

    assert "hook-run-missing" in _codes(path)


def test_a_stage_farrier_does_not_wire_is_an_error(tmp_path):
    path = _skill(tmp_path, "hooks:\n  - stage: pre-push\n    run: scripts/check.py\n")

    codes = _codes(path)
    assert "hook-unknown-stage" in codes


def test_the_error_names_the_stages_that_are_accepted(tmp_path):
    """A vocabulary error that does not print the vocabulary makes the author guess."""
    path = _skill(tmp_path, "hooks:\n  - stage: pre-push\n    run: scripts/check.py\n")

    messages = " ".join(f.message for f in check_text(path.read_text(encoding="utf-8"), path))
    for stage in STAGES:
        assert stage in messages


@pytest.mark.parametrize(
    ("block", "code"),
    [
        ("hooks: scripts/check.py\n", "hooks-not-a-list"),
        ("hooks:\n  - scripts/check.py\n", "hook-not-a-mapping"),
        ("hooks:\n  - run: scripts/check.py\n", "hook-no-stage"),
        ("hooks:\n  - stage: pre-commit\n", "hook-no-run"),
        ("hooks:\n  - stage: pre-commit\n    run: ../../etc/evil.py\n", "hook-run-escapes"),
        ("hooks:\n  - stage: pre-commit\n    run: /etc/evil.py\n", "hook-run-escapes"),
    ],
)
def test_the_malformed_shapes_are_each_named(tmp_path, block: str, code: str):
    assert code in _codes(_skill(tmp_path, block))


def test_a_prompt_cannot_declare_hooks(tmp_path):
    """A prompt bundles no scripts, so there is nothing to install and run — and a
    declaration that can never work should fail where it was written."""
    path = tmp_path / "commit.md"
    path.write_text(f"---\ndescription: Commit\n{DECLARED}---\n\n# Commit\n", encoding="utf-8")

    assert "hooks-not-a-skill" in [
        f.code for f in check_text(path.read_text(encoding="utf-8"), path)
    ]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
