"""`doctor` holds the fixture-node grammar (`docs/okf-runbook.md`'s fixture tier) to its rules.

A `fixture` node is a named, static-checkable arrangement: `args:` is what it takes, `provides:`
is what its last step leaves behind, `needs:` is another fixture it composes on top of. Every
check here is gated to a repo that has a stack to bring up at all (`_check_fixture_grammar`
mirrors `_check_runbook`'s own gating) — a repo with no runbook has nothing a fixture arranges
state in front of.
"""

from __future__ import annotations

from pathlib import Path

from ostler import doctor
from ostler.model import load

from conftest import write

RUNBOOK = """---
type: runbook
title: QA stack
---

# QA stack

- driver: web
- entry-url: http://localhost:18099
- health-path: /healthz
- stop: docker compose down -v
- working-directory: app

## Steps

### serve

- kind: service
- run: docker compose up -d --wait
- health: curl -fsS http://localhost:18099/healthz
"""

RUNBOOK_PATH = "docs/features/app/ops/qa-stack.md"

ENDPOINT_PATH = "docs/features/acme/server.md"


def _endpoint_book(fixture_bullet: str, extra: str = "") -> str:
    return f"""---
type: endpoint
title: Acme accounts
---
# Acme accounts

## Invocations

### list-accounts
- route: `GET /api/accounts`
- fixture: {fixture_bullet}
- authorization: an adjuster reads every account on file.
{extra}"""


def _fixture_book(*, args: str = "", provides: str = "", needs: str = "",
                   step_kind: str = "seed", secrets: str = "", no_run: bool = False) -> str:
    lines = ["---", "type: fixture", "title: Seeded acme", "---", "# Seeded acme", ""]
    if args:
        lines.append(f"- args: {args}")
    if provides:
        lines += ["- provides:"] + [f"  - {p}" for p in provides.split(";")]
    if needs:
        lines += ["- needs:"] + [f"  - {n}" for n in needs.split(";")]
    if secrets:
        lines += ["- secrets:"] + [f"  - {s}" for s in secrets.split(";")]
    lines += ["", "## Steps", "", "### seed-it", f"- kind: {step_kind}"]
    if not no_run:
        lines.append("- run: ./scripts/seed-acme.sh")
    lines.append("")
    return "\n".join(lines)


def _findings(repo: Path, code: str) -> list[doctor.Finding]:
    return [f for f in doctor.run(load(repo)).findings if f.code == code]


def _stack(repo: Path) -> None:
    write(repo / RUNBOOK_PATH, RUNBOOK)


def test_a_book_fixture_bullet_naming_a_fixture_node_is_clean(repo: Path) -> None:
    _stack(repo)
    write(repo / "docs/features/acme/fixtures/seeded-acme.md",
          _fixture_book(args="id", provides="id — the seeded account's id"))
    write(repo / ENDPOINT_PATH, _endpoint_book("seeded-acme — an account exists"))
    assert _findings(repo, "unknown-book-fixture") == []


def test_a_book_fixture_bullet_naming_no_fixture_node_is_unknown_book_fixture(repo: Path) -> None:
    _stack(repo)
    write(repo / ENDPOINT_PATH, _endpoint_book("no-such-fixture — nobody declared this"))
    found = _findings(repo, "unknown-book-fixture")
    assert [(f.severity, f.ref) for f in found] == [("error", "no-such-fixture")]


def test_a_fixture_steps_kind_outside_seed_run_verify_is_an_error(repo: Path) -> None:
    _stack(repo)
    write(repo / "docs/features/acme/fixtures/seeded-acme.md",
          _fixture_book(args="id", provides="id — the seeded account's id", step_kind="prepare"))
    found = _findings(repo, "fixture-step-kind")
    assert [(f.severity, f.ref) for f in found] == [("error", "prepare")]


def test_a_fixture_steps_kind_of_seed_is_clean(repo: Path) -> None:
    _stack(repo)
    write(repo / "docs/features/acme/fixtures/seeded-acme.md",
          _fixture_book(args="id", provides="id — the seeded account's id", step_kind="seed"))
    assert _findings(repo, "fixture-step-kind") == []


def test_fixture_arg_mismatch_when_a_fixture_bullet_passes_an_undeclared_arg(repo: Path) -> None:
    _stack(repo)
    write(repo / "docs/features/acme/fixtures/seeded-acme.md",
          _fixture_book(args="id", provides="id — the seeded account's id"))
    write(repo / ENDPOINT_PATH, _endpoint_book("seeded-acme name=globex — an account exists"))
    found = _findings(repo, "fixture-arg-mismatch")
    assert [(f.severity, f.ref) for f in found] == [("error", "seeded-acme")]
    assert "name" in found[0].message
    assert "id" in found[0].message


def test_fixture_arg_mismatch_is_clean_when_every_arg_is_declared(repo: Path) -> None:
    _stack(repo)
    write(repo / "docs/features/acme/fixtures/seeded-acme.md",
          _fixture_book(args="id", provides="id — the seeded account's id"))
    write(repo / ENDPOINT_PATH, _endpoint_book("seeded-acme id=globex — an account exists"))
    assert _findings(repo, "fixture-arg-mismatch") == []


def test_fixture_arg_mismatch_when_a_fixture_bullet_never_passes_a_declared_arg(repo: Path) -> None:
    """The grammar has no defaults — a declared arg the binding never passes leaves a call
    without a value it requires, exactly as surely as an unknown one is a typo."""
    _stack(repo)
    write(repo / "docs/features/acme/fixtures/seeded-acme.md",
          _fixture_book(args="id name", provides="id — the seeded account's id"))
    write(repo / ENDPOINT_PATH, _endpoint_book("seeded-acme id=globex — an account exists"))
    found = _findings(repo, "fixture-arg-mismatch")
    assert [(f.severity, f.ref) for f in found] == [("error", "seeded-acme")]
    assert "name" in found[0].message


def test_fixture_arg_mismatch_applies_to_a_needs_binding(repo: Path) -> None:
    """A `needs:` binding's `name=value` tokens are checked against the CONSUMER's own
    `args:` — they land in *its* env, never the target's, which runtime always runs with
    `{}`. A binding naming something the consumer itself does not declare is flagged."""
    _stack(repo)
    write(repo / "docs/features/acme/fixtures/seeded-acme.md",
          _fixture_book(provides="id — the seeded account's id"))
    write(repo / "docs/features/acme/fixtures/seeded-globex.md",
          _fixture_book(args="acme_id", provides="id — the seeded project's id",
                        needs="[seeded-acme](seeded-acme.md) name=globex"))
    write(repo / ENDPOINT_PATH, _endpoint_book("seeded-globex acme_id=5 — a project exists"))
    found = _findings(repo, "fixture-arg-mismatch")
    assert [(f.severity, f.ref) for f in found] == [("error", "seeded-acme")]
    assert "name" in found[0].message
    assert "seeded-globex" in found[0].message


def test_fixture_arg_mismatch_is_clean_for_a_needs_binding_matching_declared_args(
    repo: Path,
) -> None:
    _stack(repo)
    write(repo / "docs/features/acme/fixtures/seeded-acme.md",
          _fixture_book(provides="id — the seeded account's id"))
    write(repo / "docs/features/acme/fixtures/seeded-globex.md",
          _fixture_book(args="id", provides="id — the seeded project's id",
                        needs="[seeded-acme](seeded-acme.md) id=globex"))
    write(repo / ENDPOINT_PATH, _endpoint_book("seeded-globex — a project exists"))
    assert _findings(repo, "fixture-arg-mismatch") == []


def test_fixture_needs_target_args_when_a_needs_target_declares_its_own_args(repo: Path) -> None:
    """Runtime always runs a needs target with `{}` — a target that declares `args:` of its
    own can never be satisfied, regardless of what the binding passes."""
    _stack(repo)
    write(repo / "docs/features/acme/fixtures/seeded-acme.md",
          _fixture_book(args="id", provides="id — the seeded account's id"))
    write(repo / "docs/features/acme/fixtures/seeded-globex.md",
          _fixture_book(provides="id — the seeded project's id",
                        needs="[seeded-acme](seeded-acme.md)"))
    write(repo / ENDPOINT_PATH, _endpoint_book("seeded-globex — a project exists"))
    found = _findings(repo, "fixture-needs-target-args")
    assert [(f.severity, f.ref) for f in found] == [("error", "seeded-acme")]


def test_fixture_needs_target_args_is_clean_when_the_target_declares_no_args(repo: Path) -> None:
    _stack(repo)
    write(repo / "docs/features/acme/fixtures/seeded-acme.md",
          _fixture_book(provides="id — the seeded account's id"))
    write(repo / "docs/features/acme/fixtures/seeded-globex.md",
          _fixture_book(provides="id — the seeded project's id",
                        needs="[seeded-acme](seeded-acme.md)"))
    write(repo / ENDPOINT_PATH, _endpoint_book("seeded-globex — a project exists"))
    assert _findings(repo, "fixture-needs-target-args") == []


def test_fixture_arg_mismatch_is_clean_when_a_caller_omits_an_arg_supplied_by_needs(
    repo: Path,
) -> None:
    """A `fixture:` caller need not pass an arg the target's own `needs:` bindings already
    supply into its env."""
    _stack(repo)
    write(repo / "docs/features/acme/fixtures/seeded-acme.md",
          _fixture_book(provides="id — the seeded account's id"))
    write(repo / "docs/features/acme/fixtures/seeded-globex.md",
          _fixture_book(args="id", provides="id — the seeded project's id",
                        needs="[seeded-acme](seeded-acme.md) id=@seeded-acme.id"))
    write(repo / ENDPOINT_PATH, _endpoint_book("seeded-globex — a project exists"))
    assert _findings(repo, "fixture-arg-mismatch") == []


def test_fixture_arg_mismatch_when_a_caller_also_passes_an_arg_supplied_by_needs(
    repo: Path,
) -> None:
    """A `fixture:` caller passing an arg the target's `needs:` bindings already supply is a
    second source for the same arg — its own finding, not silently accepted."""
    _stack(repo)
    write(repo / "docs/features/acme/fixtures/seeded-acme.md",
          _fixture_book(provides="id — the seeded account's id"))
    write(repo / "docs/features/acme/fixtures/seeded-globex.md",
          _fixture_book(args="id", provides="id — the seeded project's id",
                        needs="[seeded-acme](seeded-acme.md) id=@seeded-acme.id"))
    write(repo / ENDPOINT_PATH, _endpoint_book("seeded-globex id=5 — a project exists"))
    found = _findings(repo, "fixture-arg-mismatch")
    assert [(f.severity, f.ref) for f in found] == [("error", "seeded-globex")]
    assert "id" in found[0].message
    assert "needs" in found[0].message


def test_fixture_needs_cycle_between_two_fixtures(repo: Path) -> None:
    _stack(repo)
    write(repo / "docs/features/acme/fixtures/seeded-acme.md",
          _fixture_book(provides="id — the seeded account's id",
                        needs="[seeded-globex](seeded-globex.md)"))
    write(repo / "docs/features/acme/fixtures/seeded-globex.md",
          _fixture_book(provides="id — the seeded project's id",
                        needs="[seeded-acme](seeded-acme.md)"))
    found = _findings(repo, "fixture-needs-cycle")
    assert found and all(f.severity == "error" for f in found)


def test_fixture_needs_with_no_cycle_is_clean(repo: Path) -> None:
    _stack(repo)
    write(repo / "docs/features/acme/fixtures/seeded-globex.md",
          _fixture_book(provides="id — the seeded project's id"))
    write(repo / "docs/features/acme/fixtures/seeded-acme.md",
          _fixture_book(provides="id — the seeded account's id",
                        needs="[seeded-globex](seeded-globex.md)"))
    assert _findings(repo, "fixture-needs-cycle") == []


def test_fixture_undeclared_provides_when_a_reference_names_an_undeclared_key(repo: Path) -> None:
    _stack(repo)
    write(repo / "docs/features/acme/fixtures/seeded-acme.md",
          _fixture_book(provides="id — the seeded account's id"))
    write(repo / ENDPOINT_PATH,
          _endpoint_book("seeded-acme — an account exists",
                          extra="- verify: json_path(path=\"@seeded-acme.token\")\n"))
    found = _findings(repo, "fixture-undeclared-provides")
    assert [(f.severity, f.ref) for f in found] == [("error", "seeded-acme.token")]


def test_fixture_undeclared_provides_is_clean_for_a_declared_key(repo: Path) -> None:
    _stack(repo)
    write(repo / "docs/features/acme/fixtures/seeded-acme.md",
          _fixture_book(provides="id — the seeded account's id"))
    write(repo / ENDPOINT_PATH,
          _endpoint_book("seeded-acme — an account exists",
                          extra="- verify: json_path(path=\"@seeded-acme.id\")\n"))
    assert _findings(repo, "fixture-undeclared-provides") == []


def test_fixture_secret_name_when_a_secrets_child_is_not_an_env_var_name(repo: Path) -> None:
    _stack(repo)
    write(repo / "docs/features/acme/fixtures/seeded-acme.md",
          _fixture_book(provides="id — the seeded account's id", secrets="API-TOKEN"))
    found = _findings(repo, "fixture-secret-name")
    assert [(f.severity, f.ref) for f in found] == [("error", "API-TOKEN")]


def test_fixture_secret_name_is_clean_for_a_valid_env_var_name(repo: Path) -> None:
    _stack(repo)
    write(repo / "docs/features/acme/fixtures/seeded-acme.md",
          _fixture_book(provides="id — the seeded account's id", secrets="API_TOKEN"))
    assert _findings(repo, "fixture-secret-name") == []


def test_fixture_step_no_run_when_a_step_has_no_run_bullet(repo: Path) -> None:
    _stack(repo)
    write(repo / "docs/features/acme/fixtures/seeded-acme.md",
          _fixture_book(provides="id — the seeded account's id", no_run=True))
    found = _findings(repo, "fixture-step-no-run")
    assert [f.severity for f in found] == ["error"]


def test_fixture_step_no_run_is_clean_when_the_step_has_a_run_bullet(repo: Path) -> None:
    _stack(repo)
    write(repo / "docs/features/acme/fixtures/seeded-acme.md",
          _fixture_book(provides="id — the seeded account's id"))
    assert _findings(repo, "fixture-step-no-run") == []


def test_fixture_step_run_is_check_expression_as_command(repo: Path) -> None:
    # A fixture's own steps are shelled the same way a runbook's are (`book_fixtures` reuses
    # `runbook.step_command`), so a check call on `run:` here is the same mistake.
    _stack(repo)
    write(repo / "docs/features/acme/fixtures/seeded-acme.md",
          "---\ntype: fixture\ntitle: Seeded acme\n---\n# Seeded acme\n\n"
          "- provides:\n  - id — the seeded account's id\n\n"
          "## Steps\n\n### seed-it\n\n- kind: seed\n"
          '- run: http_status(200, path="/healthz")\n')
    found = _findings(repo, "check-expression-as-command")
    assert [f.severity for f in found] == ["error"]


def test_fixture_checks_are_skipped_with_no_stack_runbook(repo: Path) -> None:
    """No runbook claims a stack — nothing a fixture arranges state in front of, so the
    fixture-grammar checks stay silent even over an otherwise-broken fixture book."""
    write(repo / "docs/features/acme/fixtures/seeded-acme.md",
          _fixture_book(args="id", provides="id — the seeded account's id", step_kind="prepare"))
    assert _findings(repo, "fixture-step-kind") == []
