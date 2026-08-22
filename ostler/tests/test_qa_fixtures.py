"""`ostler.qa.fixtures` — the declared arrangements a plan may ask for.

Two tiers with two different failure modes, and both are static. An app-language fixture
can name a tool the repo never opted into, which would be a second door onto the process;
a Python fixture module can be declared with nothing behind it, which is the shape of the
defect declaring fixtures exists to catch. Every case below is one of those edges.
"""

from __future__ import annotations

from pathlib import Path

from ostler.qa import fixtures


def _agents_yml(root: Path, body: str) -> None:
    (root / "agents.yml").write_text(body, encoding="utf-8")


ONE_FIXTURE = """\
qa:
  tools: [node]
  fixtures:
    three-identities:
      tool: node
      args: ["auth/seed.mjs"]
      provides: "the adjuster, holder A and holder B exist in the auth emulator"
"""


def test_a_repo_with_no_qa_block_declares_no_fixtures(tmp_path: Path) -> None:
    assert fixtures.declared(tmp_path) == ({}, [])
    assert fixtures.declared_modules(tmp_path) == set()
    assert fixtures.preflight_errors(tmp_path) == []


def test_a_well_formed_fixture_resolves_to_the_invocation_it_names(tmp_path: Path) -> None:
    _agents_yml(tmp_path, ONE_FIXTURE)
    specs, errors = fixtures.declared(tmp_path)
    assert errors == []
    assert specs["three-identities"].tool == "node"
    assert specs["three-identities"].args == ("auth/seed.mjs",)
    assert specs["three-identities"].timeout == fixtures.DEFAULT_TIMEOUT
    assert fixtures.resolved(tmp_path)["three-identities"]["args"] == ["auth/seed.mjs"]


def test_a_fixture_naming_an_un_opted_in_tool_is_a_preflight_error(tmp_path: Path) -> None:
    """The containment property, and the only one that makes `fixtures:` safe to add.

    A fixture is one named invocation of a command the repo already admitted. If it could
    name any command, `fixtures:` would be a second `tools:` that nothing reviewed — so a
    fixture pointing somewhere the opt-in list does not go blocks the run rather than
    running and being noticed later.
    """
    _agents_yml(tmp_path, ONE_FIXTURE.replace("tools: [node]", "tools: [docker]"))
    problems = fixtures.preflight_errors(tmp_path)
    assert len(problems) == 1
    assert "'node'" in problems[0]
    assert "has not opted into" in problems[0]


def test_a_fixture_with_no_provides_is_rejected(tmp_path: Path) -> None:
    """`provides:` is what a scenario's `preconditions:` are read against, not decoration."""
    _agents_yml(tmp_path, ONE_FIXTURE.replace('      provides: "the adjuster, holder A and holder B exist in the auth emulator"\n', ""))
    specs, errors = fixtures.declared(tmp_path)
    assert specs == {}
    assert len(errors) == 1
    assert "`provides:`" in errors[0]


def test_a_malformed_entry_is_an_error_and_never_a_silent_skip(tmp_path: Path) -> None:
    _agents_yml(tmp_path, "qa:\n  tools: [node]\n  fixtures:\n    seeded: 'node auth/seed.mjs'\n")
    specs, errors = fixtures.declared(tmp_path)
    assert specs == {}
    assert errors == ["qa fixture 'seeded' must be a mapping, not str"]


def test_a_declared_module_with_no_file_behind_it_is_a_preflight_error(tmp_path: Path) -> None:
    _agents_yml(tmp_path, "qa:\n  fixture_modules: [claims]\n")
    specs = tmp_path / "docs" / "specs"
    specs.mkdir(parents=True)
    assert fixtures.declared_modules(tmp_path) == {"claims"}
    problems = fixtures.preflight_errors(tmp_path, spec_root=specs)
    assert len(problems) == 1
    assert "_fixtures/claims.py" in problems[0]

    (specs / fixtures.FIXTURES_DIRNAME).mkdir()
    (specs / fixtures.FIXTURES_DIRNAME / "claims.py").write_text("", encoding="utf-8")
    assert fixtures.preflight_errors(tmp_path, spec_root=specs) == []
