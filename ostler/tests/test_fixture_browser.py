"""A fixture step a browser performs: `open:` a screen, then `arrange:` acts, read by doctor, the harness context and the compiler."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ostler import doctor
from ostler.model import load
from ostler.qa import book_fixtures, fixture_browser
from ostler.qa.compile import Gap, compile_plan_gaps
from ostler.qa.context import book_context

from conftest import screen_md, write

LOGIN_PATH = "docs/features/app/login.md"
FIXTURE_PATH = "docs/features/app/fixtures/signed-in-editor.md"
NEEDING_PATH = "docs/features/app/fixtures/editor-project.md"

LOGIN_COMPONENTS = """
## Components

### sign-in

- role: button
- name: Sign in

### unnamed

- selector: `testID=unnamed`
"""


def _fixture(*arrange: str, open_line: str = "- open: [Login](../login.md)", run: str = "") -> str:
    lines = ["---", "type: fixture", "title: Signed-in editor", "---", "# Signed-in editor", "",
             "## Steps", "", "### sign-in", "", "- kind: seed"]
    if open_line:
        lines.append(open_line)
    lines += [f"- arrange: {act}" for act in arrange]
    if run:
        lines.append(f"- run: {run}")
    return "\n".join(lines) + "\n"


NEEDING = """---
type: fixture
title: Editor project
---
# Editor project

- needs:
  - [signed-in-editor](signed-in-editor.md)

## Steps

### seed-project

- kind: seed
- run: ./scripts/seed-project.sh
"""


def _book(repo: Path, fixture: str) -> None:
    write(repo / LOGIN_PATH, screen_md("login", "Login", body=LOGIN_COMPONENTS))
    write(repo / FIXTURE_PATH, fixture)


def _codes(repo: Path, code: str) -> list[str]:
    return [finding.message for finding in doctor.run(load(repo)).findings if finding.code == code]


def test_a_browser_step_opens_the_screen_route_then_performs_its_acts_in_book_order(repo: Path) -> None:
    _book(repo, _fixture('click("../login.md#sign-in")', 'fill("label=Email", value="$EMAIL")',
                         'click("role=button[name=\\"Continue\\"]")'))

    [spec] = [book_fixtures.resolved(load(repo))["signed-in-editor"]]
    [step] = spec["steps"]

    assert step["browser"] == [
        {"open": "/login", "screen": LOGIN_PATH},
        {"act": "click", "locator": {"role": "button", "name": "Sign in"}},
        {"act": "fill", "locator": {"label": "Email"}, "value": "$EMAIL"},
        {"act": "click", "locator": {"role": "button", "name": "Continue"}},
    ]
    assert "command" not in step



def test_a_browser_step_uploads_a_file_named_from_the_repository_root(repo: Path) -> None:
    write(repo / "app/fixtures/well-formed.docx", "PK")
    _book(repo, _fixture('upload("label=Document", file="app/fixtures/well-formed.docx")'))

    [step] = book_fixtures.resolved(load(repo))["signed-in-editor"]["steps"]

    assert step["browser"][1] == {
        "act": "upload", "locator": {"label": "Document"}, "value": "app/fixtures/well-formed.docx",
    }


def test_an_upload_naming_a_file_the_checkout_lacks_is_refused_before_a_lap(repo: Path) -> None:
    _book(repo, _fixture('upload("label=Document", file="app/fixtures/missing.docx")'))

    [step] = book_fixtures.resolved(load(repo))["signed-in-editor"]["steps"]

    assert "browser" not in step
    assert "names a file this checkout does not carry" in step["unperformable"]

def test_a_browser_step_the_book_cannot_state_reaches_the_harness_as_unperformable(repo: Path) -> None:
    _book(repo, _fixture('click("../login.md#unnamed")'))

    [step] = book_fixtures.resolved(load(repo))["signed-in-editor"]["steps"]

    assert "browser" not in step
    assert "declares neither a `role:` and `name:` nor a CSS `selector:`" in step["unperformable"]


def test_doctor_holds_a_browser_step_to_its_grammar(repo: Path) -> None:
    _book(repo, _fixture('click("../login.md#missing")', 'click("button.primary")',
                         open_line="- open: [Nowhere](../nowhere.md)", run="./scripts/sign-in.sh"))

    problems = _codes(repo, "fixture-browser-step")

    assert any("links no `screen`" in p for p in problems), problems
    assert any("names no component or interaction" in p for p in problems), problems
    assert any("neither a book anchor nor a locator" in p for p in problems), problems
    assert any("both `run:` and a browser act" in p for p in problems), problems
    assert _codes(repo, "fixture-step-no-run") == []


def test_a_clean_browser_step_carries_no_finding_and_needs_no_run(repo: Path) -> None:
    _book(repo, _fixture('click("../login.md#sign-in")', 'click("text=editor@example.com")'))

    assert _codes(repo, "fixture-browser-step") == []
    assert _codes(repo, "fixture-step-no-run") == []


def test_a_runbook_step_that_opens_a_screen_is_refused(repo: Path) -> None:
    write(repo / LOGIN_PATH, screen_md("login", "Login", body=LOGIN_COMPONENTS))
    write(repo / "docs/features/app/ops/qa-stack.md", """---
type: runbook
title: QA stack
---
# QA stack

## Steps

### serve

- kind: service
- open: [Login](../login.md)
""")

    [message] = _codes(repo, "browser-step-outside-fixture")

    assert "performed only by a fixture's steps" in message


def test_an_off_book_locator_names_a_role_and_name_a_label_or_a_text() -> None:
    assert fixture_browser.off_book_locator('role=button[name="Add new account"]') == {
        "role": "button", "name": "Add new account"}
    assert fixture_browser.off_book_locator("label=Email") == {"label": "Email"}
    assert fixture_browser.off_book_locator("text=editor@example.com") == {"text": "editor@example.com"}
    assert fixture_browser.off_book_locator('role=sparkle[name="x"]') is None
    assert fixture_browser.off_book_locator("button.primary") is None


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def test_the_context_names_each_fixture_that_signs_a_browser_in_and_each_that_needs_one(repo: Path) -> None:
    _book(repo, _fixture('click("../login.md#sign-in")'))
    write(repo / NEEDING_PATH, NEEDING)
    write(repo / "docs/features/app/fixtures/plain.md", NEEDING.replace(
        "- needs:\n  - [signed-in-editor](signed-in-editor.md)\n\n", "").replace("Editor project", "Plain"))
    _git(repo, "init")
    _git(repo, "-c", "user.email=qa@example.com", "-c", "user.name=QA", "add", ".")
    _git(repo, "-c", "user.email=qa@example.com", "-c", "user.name=QA", "commit", "-qm", "base")

    assert book_context(repo)["browserFixtures"] == ["editor-project", "signed-in-editor"]


def _obligation(oid: str, fixture: str) -> dict:
    return {
        "id": oid, "source": "docs/features/demo/api.md", "node": "list-projects", "nodeType": "endpoint",
        "requirement": "lists the editor's projects", "required": True,
        "locators": {"route": ["GET /api/projects"]},
        "checksDeclared": [{"call": "ok", "name": "http_status", "args": {"code": 200, "path": "/api/projects"}}],
        "fixturesDeclared": [{"name": fixture, "args": [], "provides": "an editor", "providesKeys": []}],
    }


def _gaps(fixture: str, browser_fixtures: list[str], driver: str = "http", node_type: str = "endpoint") -> list[Gap]:
    oid = "okf:docs/features/demo/api.md#list-projects:does:1"
    context = {"story": {"slug": "demo-story"}, "obligations": [{**_obligation(oid, fixture), "nodeType": node_type}],
               "navigation": {"": {"driver": driver}}, "browserFixtures": browser_fixtures}
    return [gap for gap in compile_plan_gaps(context, story="demo-story").gaps if gap.obligation_id == oid]


def test_a_browser_sign_in_on_a_claim_no_browser_drives_is_a_compile_gap() -> None:
    [gap] = _gaps("signed-in-editor", ["signed-in-editor"])

    assert gap.kind == "browser-fixture-off-browser"
    assert "signed-in-editor signs a browser in" in gap.detail


def test_a_browser_sign_in_on_a_component_of_a_web_surface_is_no_gap() -> None:
    gaps = _gaps("signed-in-editor", ["signed-in-editor"], driver="web", node_type="component")

    assert "browser-fixture-off-browser" not in {gap.kind for gap in gaps}


def test_a_browser_sign_in_on_an_endpoint_of_a_web_surface_is_a_compile_gap() -> None:
    [gap] = _gaps("signed-in-editor", ["signed-in-editor"], driver="web")

    assert gap.kind == "browser-fixture-off-browser"
    assert "performed by http" in gap.detail


def test_a_fixture_that_runs_commands_arranges_a_claim_no_browser_drives() -> None:
    assert "browser-fixture-off-browser" not in {gap.kind for gap in _gaps("seeded-editor", ["signed-in-editor"])}
