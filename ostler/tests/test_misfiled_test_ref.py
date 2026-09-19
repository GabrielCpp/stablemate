"""A `verify:` value that is well-formed under `tests:` is one distinction, decided once.

Two questions were being asked of the same value by two modules: which key does it belong
under (`checks`, composing the refusal a person reads) and may a program move it there
unattended (`autofix`, rewriting the line). Each module held its own definition, and on a
bullet citing two test files they disagreed — the finding handed back the whole check
vocabulary while `autofix` silently relocated the bullet. `checks.relocatable_to_tests` is
now the single definition, so the classification is a superset of the rewrite by
construction, and `fixable` is *asked* rather than asserted: a finding claims `ostler
autofix` clears it only where autofix actually will.
"""

from __future__ import annotations

from pathlib import Path

from ostler import autofix, checks, doctor, registry
from ostler.model import load

from conftest import screen_md, write

ENDPOINT_PATH = "docs/features/acme/server.md"
SCREEN_PATH = "docs/features/ui/dash.md"

#: Every shape a real book writes under `verify:`, with what each one is.
VALUES: dict[str, str] = {
    "`api-service/internal/account/account_test.go::Test_Create`": "citation",
    "`web-app/app/routes/home.test.tsx`, `web-app/app/routes/locale.test.tsx`": "citation",
    '`web-app/app/auth/use-publish.test.ts::describe("usePublish")': "reference, unmovable",
    "the widget row appears in the table": "prose",
    'http_status(code=201, path="/x")': "check",
}


def endpoint_doc(value: str) -> str:
    return ("---\ntype: api\nslug: s\ntitle: T\n---\n# T\n\n"
            "## Endpoints\n\n### submit\n- method: POST\n- path: /x\n"
            f"- verify: {value}\n")


def _finding(repo: Path, code: str) -> doctor.Finding | None:
    return next((f for f in doctor.run(load(repo)).findings if f.code == code), None)


def test_a_citation_run_is_reported_as_misfiled_not_as_unparsed() -> None:
    """The two-citation bullet: the value autofix moved while the finding called it unreadable."""
    value = "`web-app/app/routes/home.test.tsx`, `web-app/app/routes/locale.test.tsx`"
    parsed = checks.parse_check(value)
    assert isinstance(parsed, checks.Refusal) and parsed.kind == "misfiled-test-ref"


def test_classification_covers_every_value_autofix_would_move() -> None:
    """The containment, stated as the property rather than as the five cases below it."""
    for value in VALUES:
        if not checks.relocatable_to_tests(value):
            continue
        parsed = checks.parse_check(value)
        assert isinstance(parsed, checks.Refusal), value
        assert parsed.kind == "misfiled-test-ref", value


def test_fixable_is_true_exactly_when_autofix_moves_the_bullet(repo: Path) -> None:
    """Both directions, read off what autofix *did* — not off the predicate it shares."""
    for value in VALUES:
        write(repo / ENDPOINT_PATH, endpoint_doc(value))
        found = _finding(repo, "misfiled-test-ref") or _finding(repo, "unparsed-check")
        moved = "- tests:" in autofix.fix_text(endpoint_doc(value))
        assert bool(found and found.fixable) is moved, value


def test_a_type_that_does_not_own_tests_is_never_told_the_fix_is_automatic(
        repo: Path) -> None:
    """`screen` declares no `tests:`, so autofix leaves the bullet and the flag says so.

    The value proves itself a citation; where it would go is the part the type decides. A
    finding claiming `ostler autofix` clears it would send the builders' repair loop to an
    autofix that never touches the line.
    """
    value = "`web-app/app/routes/home.test.tsx::renders`"
    assert "tests" not in registry.declared_keys("screen")
    write(repo / SCREEN_PATH,
          screen_md("dash", "Dash", entry=True, body=f"\n- verify: {value}\n"))
    found = _finding(repo, "misfiled-test-ref")
    assert found is not None and not found.fixable
    assert "- tests:" not in autofix.fix_text(repo.joinpath(SCREEN_PATH).read_text())
