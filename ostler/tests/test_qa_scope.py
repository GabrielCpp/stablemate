"""What the obligation packet asks a QA planner to prove, and how much it hands over.

The packet used to obligate everything the graph closure could reach, at whatever size that
came to. On a nine-epic book that meant a planner reading a 670 KB file and being told to
write live scenarios against endpoints nobody had implemented — so it invented routes, and
spent its turn failing to reach them. These pin the two halves of the narrowing: which
obligations are owed evidence, and which members of the packet the reader is handed at all.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

from ostler.qa.context import CONTEXT_HEADING, build_context, validate_context, write_context
from ostler.qa.plan import load_plan, validate_v2


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _book(tmp_path: Path) -> Path:
    """A screen that documents a route but grounds no code, holding one implemented child."""
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    (tmp_path / "docs/features/demo/screen.md").write_text(
        "---\ntype: screen\ntitle: Demo Screen\n---\n# Demo Screen\n\n"
        "- route: /demo\n"
        "- entry: from the home page\n"
        "- code:\n\n"
        "## Widget\n\n"
        "- role: alert\n"
        "- name: the failure message\n"
        "- code: app/widget.ts::render\n"
        "- verify: tests/widget.test.ts::renders\n",
        encoding="utf-8",
    )
    widget = tmp_path / "app/widget.ts"
    widget.write_text('export function render() { return "old" }\n', encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    widget.write_text('export function render() { return "new" }\n', encoding="utf-8")
    return widget


def test_container_reached_only_by_closure_is_context_not_live_evidence(tmp_path: Path):
    """The changed child is owed proof; the screen that merely contains it is not.

    Both nodes land in the packet — the closure is deliberately broad and the planner should
    read the surrounding contract. Only the child was touched and only the child is grounded,
    so only the child can be exercised. Obligating the parent is how a plan ends up asserting
    against a route with no implementation behind it.
    """
    _book(tmp_path)

    packet = build_context(tmp_path, base="HEAD", source_roots={"demo": ["app"]})
    assert validate_context(packet) == []
    by_id = {item["id"]: item for item in packet["obligations"]}

    child = by_id["okf:docs/features/demo/screen.md#widget:contract"]
    assert child["required"] is True
    assert child["evidenceRequired"] == "live"

    parent = by_id["okf:docs/features/demo/screen.md:contract"]
    assert parent["required"] is False
    assert parent["evidenceRequired"] == "context"
    assert {reason["kind"] for reason in parent["reasons"]} == {"contains-impacted-node"}


def _shared_stylesheet_book(tmp_path: Path) -> Path:
    """Two widgets and a stylesheet both of them are documented against.

    One widget also grounds a symbol of its own, which is the discriminator: the change set
    edits only the stylesheet, so the *file* reaches both and no *symbol* reaches either.
    """
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    (tmp_path / "docs/features/demo/screen.md").write_text(
        "---\ntype: screen\ntitle: Demo Screen\n---\n# Demo Screen\n\n"
        "- route: /demo\n"
        "- code:\n\n"
        "## Alert\n\n"
        "- role: alert\n"
        "- code: app/app.css\n"
        "- verify: tests/alert.test.ts::styled\n\n"
        "## Banner\n\n"
        "- role: banner\n"
        "- code: app/app.css\n"
        "- verify: tests/banner.test.ts::styled\n",
        encoding="utf-8",
    )
    stylesheet = tmp_path / "app/app.css"
    stylesheet.write_text(".alert { color: red }\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    stylesheet.write_text(".alert { color: blue }\n", encoding="utf-8")
    return stylesheet


def test_a_file_cited_by_many_nodes_is_context_not_live_evidence(tmp_path: Path):
    """One edited stylesheet does not owe live proof for every component that renders through it.

    A `file-owner` reason is a bare-file citation, so it localizes the change only as far as
    the file belongs to one node. On a real run an eight-line change to `app.css` was the
    sole reason 30 of 58 nodes were owed evidence, and the planner spent three hour-long
    turns — $32 — writing plans that could never cover them, because nothing in the diff
    said what to assert.
    """
    _shared_stylesheet_book(tmp_path)

    packet = build_context(tmp_path, base="HEAD", source_roots={"demo": ["app"]})
    assert validate_context(packet) == []
    by_id = {item["id"]: item for item in packet["obligations"]}

    for node in ("alert", "banner"):
        obligation = by_id[f"okf:docs/features/demo/screen.md#{node}:contract"]
        assert obligation["required"] is False, f"{node} is owed live evidence"
        assert obligation["evidenceRequired"] == "context"
        assert {reason["kind"] for reason in obligation["reasons"]} == {"file-owner"}


def test_a_file_owned_by_one_node_still_owes_live_evidence(tmp_path: Path):
    """The narrowing is about a citation that stopped discriminating, not about bare files.

    A language whose symbols the mapper cannot extract reaches its node by file and nothing
    else. While that node is the file's only owner the citation still says exactly what the
    change touched, so demoting it would leave the change with no obligation at all.
    """
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    (tmp_path / "docs/features/demo/screen.md").write_text(
        "---\ntype: screen\ntitle: Demo Screen\n---\n# Demo Screen\n\n"
        "- route: /demo\n"
        "- code:\n\n"
        "## Alert\n\n"
        "- role: alert\n"
        "- code: app/alert.css\n"
        "- verify: tests/alert.test.ts::styled\n",
        encoding="utf-8",
    )
    stylesheet = tmp_path / "app/alert.css"
    stylesheet.write_text(".alert { color: red }\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    stylesheet.write_text(".alert { color: blue }\n", encoding="utf-8")

    packet = build_context(tmp_path, base="HEAD", source_roots={"demo": ["app"]})
    obligation = {item["id"]: item for item in packet["obligations"]}[
        "okf:docs/features/demo/screen.md#alert:contract"
    ]
    assert obligation["required"] is True
    assert obligation["evidenceRequired"] == "live"


def _shared_container_book(tmp_path: Path) -> Path:
    """Three controls documented against one toolbar component, one of them brand new.

    Every control cites the container symbol, because the container is where it is rendered
    and the honest anchor for it. Only the new control also cites a symbol of its own.
    """
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    (tmp_path / "docs/features/demo/screen.md").write_text(
        "---\ntype: screen\ntitle: Demo Screen\n---\n# Demo Screen\n\n"
        "- route: /demo\n"
        "- code:\n\n"
        "## Undo\n\n"
        "- role: button\n"
        "- name: Undo\n"
        "- code: app/toolbar.ts::Toolbar\n"
        "- verify: tests/toolbar.test.ts::undoes\n\n"
        "## Redo\n\n"
        "- role: button\n"
        "- name: Redo\n"
        "- code: app/toolbar.ts::Toolbar\n"
        "- verify: tests/toolbar.test.ts::redoes\n\n"
        "## Publish\n\n"
        "- role: button\n"
        "- name: Publish\n"
        "- code: app/toolbar.ts::Toolbar\n"
        "- code: app/toolbar.ts::PublishButton\n"
        "- verify: tests/toolbar.test.ts::publishes\n",
        encoding="utf-8",
    )
    toolbar = tmp_path / "app/toolbar.ts"
    toolbar.write_text("export function Toolbar() { return 'undo redo' }\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    toolbar.write_text(
        "export function PublishButton() { return 'publish' }\n"
        "export function Toolbar() { return 'undo redo publish' }\n",
        encoding="utf-8",
    )
    return toolbar


def test_a_symbol_cited_by_many_nodes_is_context_not_live_evidence(tmp_path: Path):
    """Adding one control to a toolbar does not owe live proof of every control on it.

    An exact symbol localizes better than a bare file but not perfectly: a container cited
    by a dozen nodes marks all of them changed when one new control is rendered inside it.
    On a real run a story that added a publish button was charged with proving undo, redo
    and four heading and list toggles it never touched — 70 of the plan's obligations, all
    held by the one toolbar symbol — and the planner burned its whole validation budget
    writing scenarios the change could not justify.
    """
    _shared_container_book(tmp_path)

    packet = build_context(tmp_path, base="HEAD", source_roots={"demo": ["app"]})
    assert validate_context(packet) == []
    by_id = {item["id"]: item for item in packet["obligations"]}

    for node in ("undo", "redo"):
        obligation = by_id[f"okf:docs/features/demo/screen.md#{node}:contract"]
        assert obligation["required"] is False, f"{node} is owed live evidence"
        assert obligation["evidenceRequired"] == "context"

    published = by_id["okf:docs/features/demo/screen.md#publish:contract"]
    assert published["required"] is True
    assert published["evidenceRequired"] == "live"


def _event_book(tmp_path: Path) -> Path:
    """A changed producer, and an untouched consumer the relation fixpoint walks to.

    The consumer grounds its own code and that code is not in the diff. Nothing about this
    story says what to assert about it — only that it listens to a name the producer says.
    """
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    (tmp_path / "docs/features/demo/producer.md").write_text(
        "---\ntype: screen\ntitle: Checkout\n---\n# Checkout\n\n"
        "- route: /checkout\n"
        "- code:\n\n"
        "## Place\n\n"
        "- role: button\n"
        "- name: Place order\n"
        "- emits: order.placed\n"
        "- code: app/producer.py::place\n"
        "- verify: tests/producer_test.py::places\n",
        encoding="utf-8",
    )
    (tmp_path / "docs/features/demo/consumer.md").write_text(
        "---\ntype: screen\ntitle: Receipts\n---\n# Receipts\n\n"
        "- route: /receipts\n"
        "- code:\n\n"
        "## Mail\n\n"
        "- role: status\n"
        "- name: Receipt sent\n"
        "- consumes: order.placed\n"
        "- code: app/consumer.py::mail\n"
        "- verify: tests/consumer_test.py::mails\n",
        encoding="utf-8",
    )
    producer = tmp_path / "app/producer.py"
    producer.write_text("def place():\n    return 'old'\n", encoding="utf-8")
    (tmp_path / "app/consumer.py").write_text("def mail():\n    return 'sent'\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    producer.write_text("def place():\n    return 'new'\n", encoding="utf-8")
    return producer


def test_a_node_reached_only_by_the_event_fixpoint_is_context_not_live_evidence(tmp_path: Path):
    """Sharing an event name with the change is closure, not reach.

    The `while related:` fixpoint walks `emits`/`consumes` and the consistency bullets until
    nothing new is reachable, and never consults the diff while doing it — so every kind it
    mints is closure by construction. Left owed live evidence, a seven-criterion story came
    out demanding proof across 67 documents: 194 of its obligations were held by
    `event-consumer` alone, the planner could not write a plan that covered them, the
    reviewer was right to keep rejecting it, and the story ended with no verdict at all.
    """
    _event_book(tmp_path)

    packet = build_context(tmp_path, base="HEAD", source_roots={"demo": ["app"]})
    assert validate_context(packet) == []
    by_id = {item["id"]: item for item in packet["obligations"]}

    producer = by_id["okf:docs/features/demo/producer.md#place:contract"]
    assert producer["required"] is True
    assert producer["evidenceRequired"] == "live"

    consumer = by_id["okf:docs/features/demo/consumer.md#mail:contract"]
    assert {reason["kind"] for reason in consumer["reasons"]} == {"event-consumer"}
    assert consumer["required"] is False
    assert consumer["evidenceRequired"] == "context"


def test_every_relation_fixpoint_kind_is_declared_closure(tmp_path: Path):
    """The set and the loop that feeds it may not drift apart again.

    They already did once: the fixpoint was added with seven relation bullets plus the two
    event kinds, and none of the nine was added to the exemption. Deriving the reason kinds
    from the same tuple the loop iterates is what makes that unrepeatable, and this asserts
    the derivation rather than a re-typed literal.
    """
    from ostler.qa.context import (
        _CLOSURE_REASON_KINDS,
        _RELATION_KEYS,
        _RELATION_REASON_KINDS,
    )

    assert _RELATION_REASON_KINDS == {key.replace(" ", "-") for key in _RELATION_KEYS}
    assert _RELATION_REASON_KINDS <= _CLOSURE_REASON_KINDS
    assert {"event-consumer", "event-producer"} <= _CLOSURE_REASON_KINDS


def test_qa_scaffolding_is_not_a_production_unit():
    """QA does not owe live proof of the mock backend it tests through.

    Six of one story's sixteen changed files were `tools/qa-mock-backends/*.py`. None of the
    filter's tokens (`test`, `fixtures`, `__mocks__`) appears in that path, so the mocks were
    modelled as product, and roughly half the story's surviving live obligations were owed
    against the fixture harness and mock servers. The plan's first scenario asserted the
    fixture server's own routes.
    """
    from ostler.qa.context import _is_non_production_path as non_production

    assert non_production("web-app/tools/qa-mock-backends/auth.py")
    assert non_production("web/mocks/handlers.ts")
    assert non_production("web/__mocks__/handlers.ts")
    assert non_production("svc/stubs/payments.go")
    assert non_production("e2e/harness/browser.ts")
    assert non_production("svc/fake-clock/clock.go")
    assert non_production("web/api-mocks/orders.ts")

    assert not non_production("app/mock.py")
    assert not non_production("app/services/payments.py")
    assert not non_production("web/src/components/Banner.tsx")


def test_obligations_carry_the_book_locators_for_the_node(tmp_path: Path):
    """`role`/`name`/`route` ride on the obligation, so a browser locator has a source.

    Every locator in every plan written before this was a text match on a rendered string —
    the book's accessible names were enforced as a coverage checkbox and never read as
    addresses.
    """
    _book(tmp_path)

    packet = build_context(tmp_path, base="HEAD", source_roots={"demo": ["app"]})
    by_id = {item["id"]: item for item in packet["obligations"]}

    assert by_id["okf:docs/features/demo/screen.md#widget:contract"]["locators"] == {
        "role": ["alert"],
        "name": ["the failure message"],
    }
    assert by_id["okf:docs/features/demo/screen.md:contract"]["locators"] == {
        "route": ["/demo"],
        "entry": ["from the home page"],
    }


def test_write_context_moves_the_verification_index_to_a_sidecar(tmp_path: Path):
    """One row per `verify:` ref in the whole book — machine input, not reading material.

    It is the largest member of the packet and the only one no reader consumes, so it goes
    beside the file the planner reads rather than inside it.
    """
    _book(tmp_path)
    packet = build_context(tmp_path, base="HEAD", source_roots={"demo": ["app"]})
    assert packet["verificationIndex"], "fixture must produce an index to relocate"

    spec_dir = tmp_path / "docs/specs/story-1"
    json_path, md_path = write_context(packet, spec_dir)

    written = json.loads(json_path.read_text(encoding="utf-8"))
    assert "verificationIndex" not in written
    assert validate_context(written) == []

    sidecar = json.loads((spec_dir / "qa-okf-verification-index.json").read_text(encoding="utf-8"))
    assert sidecar == packet["verificationIndex"]
    # The context-only entries survive the sidecar split, under their own heading.
    assert CONTEXT_HEADING in md_path.read_text(encoding="utf-8")


def _plan_covering(spec: Path, obligation: str) -> Path:
    plan = {
        "version": 2,
        "run_id": "qa-run-1",
        "story": "story-1",
        "targets": {"api": {"driver": "command"}},
        "scenarios": [
            {
                "id": "api-contract",
                "target": "api",
                "mechanism": "live",
                "covers": [obligation],
                "actions": [
                    {
                        "do": "command",
                        "id": "emit",
                        "cmd": "printf '{\"value\":\"ok\"}'",
                        "assert_contains": "ok",
                        "out": "qa/steps/emit.json",
                    }
                ],
            }
        ],
    }
    path = spec / "qa-plan.yml"
    path.write_text(yaml.safe_dump(plan, sort_keys=False), encoding="utf-8")
    return path


def _context_with(spec: Path, *, required: bool) -> None:
    spec.mkdir(parents=True, exist_ok=True)
    obligations = [
        {
            "id": "okf:docs/features/demo/item.md:contract",
            "kind": "contract",
            "node": "item",
            "source": "docs/features/demo/item.md",
            "requirement": "item is emitted",
            "required": True,
            "evidenceRequired": "live",
            "reasons": [],
        },
        {
            "id": "okf:docs/features/demo/unbuilt.md:contract",
            "kind": "contract",
            "node": "unbuilt",
            "source": "docs/features/demo/unbuilt.md",
            "requirement": "an endpoint nobody has written",
            "required": required,
            "evidenceRequired": "live" if required else "context",
            "reasons": [{"kind": "flow-contract-closure", "ref": "flow"}],
        },
    ]
    (spec / "qa-okf-context.json").write_text(
        json.dumps(
            {
                "version": 1,
                "available": True,
                "base": "base",
                "head": "head",
                "changedCode": [],
                "directNodes": [],
                "contracts": [],
                "journeys": [],
                "journeyNodes": [],
                "verificationRefs": [],
                "healthFindings": [],
                "acceptanceCriteria": [],
                "obligations": obligations,
            }
        ),
        encoding="utf-8",
    )


def test_coverage_gate_skips_context_only_obligations(tmp_path: Path):
    """A plan covering only what the story built validates; the same plan used to be rejected.

    The rejection is what drove the rework loop — the planner could not satisfy the gate
    without writing a scenario against something unimplemented, so it wrote one, and the
    scenario failed.
    """
    spec = tmp_path / "docs/specs/story-1"
    _context_with(spec, required=False)
    plan = _plan_covering(spec, "okf:docs/features/demo/item.md:contract")

    document, load_problems = load_plan(plan, spec, tmp_path)
    assert not load_problems and document is not None
    assert not [item for item in validate_v2(document) if "unbuilt.md" in item]


_GUI = "okf:docs/features/demo/screen.md#widget:contract"


def _gui_context(spec: Path, *, role: str = "alert", route: str = "/demo") -> None:
    spec.mkdir(parents=True, exist_ok=True)
    (spec / "qa-okf-context.json").write_text(
        json.dumps(
            {
                "version": 1,
                "available": True,
                "base": "base",
                "head": "head",
                "changedCode": [],
                "directNodes": [],
                "contracts": [],
                "journeys": [],
                "journeyNodes": [],
                "verificationRefs": [],
                "healthFindings": [],
                "acceptanceCriteria": [],
                "obligations": [
                    {
                        "id": _GUI,
                        "kind": "contract",
                        "node": "widget",
                        "source": "docs/features/demo/screen.md",
                        "requirement": "the failure message is shown",
                        "required": True,
                        "evidenceRequired": "live",
                        "reasons": [{"kind": "changed-code", "ref": "app/widget.ts::render"}],
                        "locators": {"role": [role], "name": ["the failure message"], "route": [route]},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _gui_plan(spec: Path, *, locator: dict, url: str = "/demo") -> Path:
    plan = {
        "version": 2,
        "run_id": "qa-run-1",
        "story": "story-1",
        "targets": {"web": {"driver": "playwright", "base_url": "http://127.0.0.1:8000"}},
        "scenarios": [
            {
                "id": "widget-visible",
                "target": "web",
                "mechanism": "live",
                "covers": [_GUI],
                "actions": [
                    {"do": "goto", "id": "open", "url": url},
                    {"expect": "visible", "id": "shown", "locator": locator},
                ],
            }
        ],
    }
    path = spec / "qa-plan.yml"
    path.write_text(yaml.safe_dump(plan, sort_keys=False), encoding="utf-8")
    return path


def _problems(tmp_path: Path, plan: Path, spec: Path) -> list[str]:
    document, load_problems = load_plan(plan, spec, tmp_path)
    assert not load_problems and document is not None
    return validate_v2(document)


def test_book_locator_plan_validates(tmp_path: Path):
    """The compliant shape: addressed by the documented role, on the documented route."""
    spec = tmp_path / "docs/specs/story-1"
    _gui_context(spec)
    plan = _gui_plan(spec, locator={"role": "alert", "name": "the failure message"})

    assert not [item for item in _problems(tmp_path, plan, spec) if "widget-visible" in item]


def test_text_locator_is_rejected_when_the_book_states_a_role(tmp_path: Path):
    """The exact defect: a text match on a rendered string where the book gave an address."""
    spec = tmp_path / "docs/specs/story-1"
    _gui_context(spec)
    plan = _gui_plan(spec, locator={"text": "Something went wrong"})

    problems = _problems(tmp_path, plan, spec)
    assert any("uses a text locator" in item and "'alert'" in item for item in problems)


def test_unaddressed_documented_role_is_rejected(tmp_path: Path):
    """A CSS escape hatch does not satisfy a documented role either."""
    spec = tmp_path / "docs/specs/story-1"
    _gui_context(spec)
    plan = _gui_plan(spec, locator={"css": ".error-banner"})

    problems = _problems(tmp_path, plan, spec)
    assert any("no Playwright locator addresses by role" in item for item in problems)


def test_navigation_to_an_undocumented_route_is_rejected(tmp_path: Path):
    """The other half of "we test routes that do not exist" — invented URLs."""
    spec = tmp_path / "docs/specs/story-1"
    _gui_context(spec)
    plan = _gui_plan(
        spec, locator={"role": "alert", "name": "the failure message"}, url="/admin/settings"
    )

    problems = _problems(tmp_path, plan, spec)
    assert any("is not a route documented" in item for item in problems)


def test_documented_route_parameters_match_a_filled_url(tmp_path: Path):
    """`/docs/:slug` must accept `/docs/{{slug}}` — the gate cannot forbid parameterised routes."""
    spec = tmp_path / "docs/specs/story-1"
    _gui_context(spec, route="/docs/:slug")
    plan = _gui_plan(
        spec, locator={"role": "alert", "name": "the failure message"}, url="/docs/{{slug}}"
    )

    assert not [item for item in _problems(tmp_path, plan, spec) if "not a route" in item]


def test_text_is_allowed_when_a_covered_node_has_no_documented_address(tmp_path: Path):
    """No dead ends: a node the book gives no address for still needs a text locator."""
    spec = tmp_path / "docs/specs/story-1"
    _gui_context(spec)
    packet = json.loads((spec / "qa-okf-context.json").read_text())
    packet["obligations"].append(
        {**packet["obligations"][0], "id": "okf:docs/features/demo/screen.md:contract", "locators": {}}
    )
    (spec / "qa-okf-context.json").write_text(json.dumps(packet), encoding="utf-8")
    plan = _gui_plan(spec, locator={"role": "alert", "name": "the failure message"})
    document = yaml.safe_load(plan.read_text())
    document["scenarios"][0]["covers"].append("okf:docs/features/demo/screen.md:contract")
    document["scenarios"][0]["actions"].append({"expect": "visible", "id": "also", "locator": {"text": "Demo"}})
    plan.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    assert not [item for item in _problems(tmp_path, plan, spec) if "text locator" in item]


def test_absent_role_bullet_imposes_no_locator_rule(tmp_path: Path):
    """`role: n/a` is the book saying there is no control — not an address to enforce."""
    spec = tmp_path / "docs/specs/story-1"
    _gui_context(spec, role="n/a")
    plan = _gui_plan(spec, locator={"text": "The requested page could not be found."})

    problems = _problems(tmp_path, plan, spec)
    assert not [item for item in problems if "text locator" in item or "by role" in item]


def test_coverage_gate_still_demands_required_obligations(tmp_path: Path):
    """The narrowing is the flag, not the reason kind — a required obligation stays required.

    Absent the flag entirely the gate must also hold, so a packet written before the split
    keeps failing loudly rather than silently passing everything.
    """
    spec = tmp_path / "docs/specs/story-1"
    _context_with(spec, required=True)
    plan = _plan_covering(spec, "okf:docs/features/demo/item.md:contract")

    document, load_problems = load_plan(plan, spec, tmp_path)
    assert not load_problems and document is not None
    problems = validate_v2(document)
    assert any("unbuilt.md" in item and "not covered" in item for item in problems)

    del document.context["obligations"][1]["required"]
    assert any("unbuilt.md" in item and "not covered" in item for item in validate_v2(document))


def _two_flows_over_one_contract(tmp_path: Path) -> Path:
    """Two sibling journeys over the same changed contract, one of them linking to the other.

    The shape is ordinary in a real book: a broad journey names a narrower one as a step, and
    both walk the same endpoint. It is also the shape that files the narrower flow under both
    roles at once.
    """
    (tmp_path / "docs/features/demo/flows").mkdir(parents=True)
    (tmp_path / "docs/features/demo/http").mkdir()
    (tmp_path / "app").mkdir()
    (tmp_path / "docs/features/demo/http/api.md").write_text(
        "---\ntype: endpoint\nslug: api\ntitle: Read API\n---\n# Read API\n\n"
        "- does: serves the stored object verbatim\n"
        "- code: app/api.go::Read\n"
        "- verify: tests/api_test.go::TestRead\n",
        encoding="utf-8",
    )
    (tmp_path / "docs/features/demo/flows/serves-object.md").write_text(
        "---\ntype: flow\nslug: serves-object\ntitle: Serves object\n---\n# Serves object\n\n"
        "- start: a caller issues the read request\n"
        "- steps:\n"
        "  1. [Read API](../http/api.md) returns the object\n"
        "- end: the caller receives the object verbatim\n",
        encoding="utf-8",
    )
    (tmp_path / "docs/features/demo/flows/cold-start.md").write_text(
        "---\ntype: flow\nslug: cold-start\ntitle: Cold start\n---\n# Cold start\n\n"
        "- start: the app boots\n"
        "- steps:\n"
        "  1. [Read API](../http/api.md) answers\n"
        "  2. as [Serves object](./serves-object.md) describes\n"
        "- end: the app has rendered\n",
        encoding="utf-8",
    )
    api = tmp_path / "app/api.go"
    api.write_text("package app\n\nfunc Read() string { return \"old\" }\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    api.write_text("package app\n\nfunc Read() string { return \"new\" }\n", encoding="utf-8")
    return api


def test_a_flow_linked_from_another_flow_is_not_also_a_contract(tmp_path: Path):
    """A journey reached by the closure is filed once, so its bullets obligate once.

    `_obligations` runs per member of `contracts` and per member of `journeys`, and only the
    base obligation spells the role into its id. A flow in both sets therefore emits one
    `:contract` and one `:end-state` — harmless — and two identical `:start:1` and `:end:1`,
    which is a duplicate id. `validate_context` rejects the packet for it, and the
    documentation gate turns that rejection into a rework brief the author cannot satisfy:
    nothing is wrong with the book, so every pass writes something and fails the same way
    until the rework budget runs out and the run dies.
    """
    _two_flows_over_one_contract(tmp_path)

    packet = build_context(tmp_path, base="HEAD", source_roots={"demo": ["app"]})

    linked = "docs/features/demo/flows/serves-object.md"
    assert linked in packet["journeys"]
    assert linked not in packet["contracts"]
    assert not [node for node in packet["contracts"] if "/flows/" in node]

    ids = [item["id"] for item in packet["obligations"]]
    assert sorted(set(ids)) == sorted(ids)
    assert validate_context(packet) == []
