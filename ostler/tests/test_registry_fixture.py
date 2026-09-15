"""`registry`'s fixture-node grammar and the `capture:` bullet it shares with `verify:`/`fixture:`.

A `fixture` node is a file-level `fixtures` type reusing the `step` section for its own
`## Steps`. `capture:` is the mirror-image flag of `arrange`/`check` on the same seven node
types that already carry `fixture:`/`verify:`, and its attribution
(`capture_keys`/`attributed_captures`) is required to delegate to the same `_attributed` engine
`attributed_fixtures`/`attributed_checks` already use — not a second one.
"""

from __future__ import annotations

from pathlib import Path

from ostler import doctor, registry
from ostler.model import load

from conftest import write

CAPTURE_NODE_TYPES = (
    "environment", "command", "endpoint", "interaction", "invocation", "method", "field",
)


def all_codes(report):
    return {f.code for f in report.findings}


def _run(repo: Path):
    return doctor.run(load(repo))


def test_fixture_node_type_is_registered_as_a_fixtures_file() -> None:
    uitype = registry.UI_TYPES_BY_NAME["fixture"]
    assert uitype.kind == "file"
    assert uitype.context == "fixtures"
    assert {b.key for b in uitype.bullet_keys} == {"args", "provides", "needs", "secrets"}
    needs = next(b for b in uitype.bullet_keys if b.key == "needs")
    provides = next(b for b in uitype.bullet_keys if b.key == "provides")
    assert needs.link is True and needs.nested is True
    assert provides.nested is True and provides.link is False


def test_capture_is_declared_on_exactly_the_seven_fixture_and_verify_types() -> None:
    for node_type in CAPTURE_NODE_TYPES:
        assert "capture" in registry.capture_keys(node_type), node_type
        assert "fixture" in registry.arrange_keys(node_type), node_type

    for node_type in ("fixture", "concept", "format", "screen", "cli", "server", "step"):
        assert "capture" not in registry.capture_keys(node_type), node_type


def test_a_fixture_node_parses_args_provides_needs_with_no_unknown_bullet(repo: Path) -> None:
    write(repo / "docs/features/acme/fixtures/seeded-acme.md",
          "---\ntype: fixture\ntitle: Seeded acme\n---\n# Seeded acme\n\n"
          "- args: id\n"
          "- provides:\n  - id — the seeded account's id\n"
          "\n## Steps\n\n### seed-it\n- kind: seed\n- run: ./scripts/seed-acme.sh\n")
    write(repo / "docs/features/acme/fixtures/seeded-globex.md",
          "---\ntype: fixture\ntitle: Seeded globex\n---\n# Seeded globex\n\n"
          "- provides:\n  - id — the seeded project's id\n"
          "- needs:\n  - [seeded-acme](seeded-acme.md)\n"
          "\n## Steps\n\n### seed-it\n- kind: seed\n- run: ./scripts/seed-globex.sh\n")
    report = _run(repo)
    assert "unknown-bullet" not in all_codes(report)
    fixtures = load(repo).ui_nodes_of_type("fixture")
    assert {Path(n.id).stem for n in fixtures} == {"seeded-acme", "seeded-globex"}


def test_attributed_captures_mirrors_attributed_fixtures_via_the_shared_engine(
    repo: Path,
) -> None:
    write(repo / "docs/features/acme/server.md",
          "---\ntype: endpoint\ntitle: Acme accounts\n---\n# Acme accounts\n\n"
          "## Invocations\n\n### list-accounts\n"
          "- route: `GET /api/accounts`\n"
          "- does:\n  - lists every account on file\n"
          "- capture: account_id from $.accounts[0].id\n")
    inv = load(repo).ui_nodes_of_type("invocation")[0]
    _, per_bullet = registry.attributed_captures(inv.type, inv.bullet_order)
    assert per_bullet == {("does", 1): ["account_id from $.accounts[0].id"]}

    # Same shape `attributed_fixtures`/`attributed_checks` return — same engine, different key.
    fixtures_shape = registry.attributed_fixtures(inv.type, inv.bullet_order)
    checks_shape = registry.attributed_checks(inv.type, inv.bullet_order)
    captures_shape = registry.attributed_captures(inv.type, inv.bullet_order)
    assert type(fixtures_shape) is type(checks_shape) is type(captures_shape)


def test_a_fixture_nodes_own_steps_do_not_carry_capture() -> None:
    step_type = registry.UI_TYPES_BY_NAME["step"]
    assert "capture" not in {b.key for b in step_type.bullet_keys}
