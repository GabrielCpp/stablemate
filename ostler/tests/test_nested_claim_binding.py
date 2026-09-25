"""A `verify:` or `fixture:` indented under one child of a claim list binds to that child alone."""

from __future__ import annotations

from pathlib import Path

from ostler import doctor, registry
from ostler.model import UINode, load

from conftest import write

PAGE = "---\ntype: cli\nslug: tally\ntitle: Tally\n---\n# Tally\n\n## Commands\n\n### add\n"

LISTED = PAGE + (
    "- does:\n"
    "  - Records one expense.\n"
    "    - fixture: existing-ledger\n"
    '    - verify: count(subject="$.entries", equals=1, file="tally.json")\n'
    "  - Reports the amount on stderr.\n"
    '    - verify: stderr(matches="added")\n'
    '- verify: stdout(matches="ok")\n'
)

BRANCHES = PAGE + (
    "- does: branches\n"
    "  - success: Records one expense.\n"
    '    - verify: stdout(matches="added")\n'
    "  - failure: Refuses without a ledger.\n"
    '    - verify: stderr(matches="no ledger")\n'
)


def _command(repo: Path, text: str) -> UINode:
    write(repo / "docs/features/tally/cli/tally.md", text)
    return load(repo).ui_nodes_of_type("command")[0]


def _codes(repo: Path) -> set[str]:
    return {f.code for f in doctor.run(load(repo)).findings}


def test_a_nested_check_binds_to_its_own_child_and_a_beside_check_fans_out(tmp_path: Path) -> None:
    node = _command(tmp_path, LISTED)
    _, per_claim = registry.attributed_checks(node.type, node.bullet_order, node.combiners)
    assert per_claim == {
        ("does", 1): ['count(subject="$.entries", equals=1, file="tally.json")', 'stdout(matches="ok")'],
        ("does", 2): ['stderr(matches="added")', 'stdout(matches="ok")'],
    }


def test_a_nested_fixture_arranges_its_own_child_alone(tmp_path: Path) -> None:
    node = _command(tmp_path, LISTED)
    _, per_claim = registry.attributed_fixtures(node.type, node.bullet_order, node.combiners)
    assert per_claim == {("does", 1): ["existing-ledger"]}


def test_listed_checks_leave_out_the_checks_nested_under_one_child(tmp_path: Path) -> None:
    node = _command(tmp_path, LISTED)
    assert registry.listed_checks(node.type, node.bullet_order) == {
        ("does", 1): ['stdout(matches="ok")'],
        ("does", 2): ['stdout(matches="ok")'],
    }


def test_the_meta_files_a_nested_check_under_its_own_key(tmp_path: Path) -> None:
    node = _command(tmp_path, LISTED)
    assert node.meta["does"] == ["Records one expense.", "Reports the amount on stderr."]
    assert node.meta["fixture"] == "existing-ledger"
    assert node.meta["verify"] == [
        'count(subject="$.entries", equals=1, file="tally.json")',
        'stderr(matches="added")',
        'stdout(matches="ok")',
    ]


def test_nested_checks_declare_the_listed_claims_obligations(tmp_path: Path) -> None:
    _command(tmp_path, LISTED.replace('- verify: stdout(matches="ok")\n', ""))
    assert "undeclared-obligation" not in _codes(tmp_path)


def test_each_branch_is_observed_by_the_check_nested_under_it(tmp_path: Path) -> None:
    node = _command(tmp_path, BRANCHES)
    _, per_claim = registry.attributed_checks(node.type, node.bullet_order, node.combiners)
    assert per_claim == {
        ("does", 1): ['stdout(matches="added")'],
        ("does", 2): ['stderr(matches="no ledger")'],
    }
    assert "unobserved-branch" not in _codes(tmp_path)


def test_a_check_beside_a_branches_list_still_observes_no_branch(tmp_path: Path) -> None:
    _command(tmp_path, PAGE + (
        "- does: branches\n"
        "  - success: Records one expense.\n"
        "  - failure: Refuses without a ledger.\n"
        '- verify: stdout(matches="added")\n'
    ))
    assert "unobserved-branch" in _codes(tmp_path)
