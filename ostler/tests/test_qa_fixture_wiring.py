"""An end-to-end check that `context.py`'s fixture wiring — `_fixture_provides_index`, `_parse_captures`, the `needs`-edge lookup, and ambient fixtures picking up `providesKeys` — is actually exercised over a real on-disk book, not just over hand-built packet fields the way every other `compile_plan_gaps` test in this tree constructs its fixtures."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ostler import doctor
from ostler.model import load
from ostler.qa.compile import compile_plan, compile_plan_gaps
from ostler.qa.context import build_context

from conftest import write

RUNBOOK = """---
type: runbook
title: QA stack
---

# QA stack

- driver: http
- surfaces: [Acme projects](../../acme/server.md)
- entry-url: http://localhost:18101
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

SEEDED_ACME = """---
type: fixture
title: Seeded acme
---
# Seeded acme

- provides:
  - id — the seeded account's id
    - from: [seed-it](#seed-it)
    - read: account.id

## Steps

### seed-it

- kind: seed
- run: ./scripts/seed-acme.sh
"""

SEEDED_ACME_PATH = "docs/features/acme/fixtures/seeded-acme.md"

SEEDED_GLOBEX = """---
type: fixture
title: Seeded globex
---
# Seeded globex

- provides:
  - project_id — the seeded project's id
    - from: [seed-it](#seed-it)
    - read: project.id
- needs:
  - [seeded-acme](seeded-acme.md)

## Steps

### seed-it

- kind: seed
- run: ./scripts/seed-globex.sh
"""

SEEDED_GLOBEX_PATH = "docs/features/acme/fixtures/seeded-globex.md"

ENDPOINT_PATH = "docs/features/acme/server.md"


def _endpoint_book(*, capture: bool) -> str:
    capture_line = "- capture: name from $.project.name\n" if capture else ""
    return f"""---
type: server
title: Acme projects
---
# Acme projects

- entry-url: http://localhost:18101

## Endpoints

### create-project

- method: GET
- path: /api/accounts/@seeded-acme.id/projects
- does: a project is created for the seeded account.
- fixture: seeded-globex
{capture_line}- verify: http_status(code=201)
- status: the created project is returned.
- code: app/service.py::create_project
- verify: json_path(path="@seeded-globex.project_id", matches="$name")
"""


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _write_source(root: Path, body: str) -> None:
    write(root / "app/service.py", body)


def _commit_base(root: Path) -> str:
    _git(root, "init")
    _git(root, "config", "user.email", "qa@example.com")
    _git(root, "config", "user.name", "QA")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "base")
    return _git(root, "rev-parse", "HEAD")


def _build(root: Path, *, capture: bool) -> tuple[dict, str]:
    write(root / RUNBOOK_PATH, RUNBOOK)
    write(root / SEEDED_ACME_PATH, SEEDED_ACME)
    write(root / SEEDED_GLOBEX_PATH, SEEDED_GLOBEX)
    write(root / ENDPOINT_PATH, _endpoint_book(capture=capture))
    _write_source(root, "def create_project():\n    return 'old'\n")
    base = _commit_base(root)

    _write_source(root, "def create_project():\n    return 'new'\n")

    packet = build_context(root, base=base, source_roots={"acme": ["app"]})
    return packet, base


def test_fixture_wiring_resolves_every_reference_over_a_real_book(tmp_path: Path) -> None:
    packet, _base = _build(tmp_path, capture=True)
    result = compile_plan_gaps(packet, story="demo-story")
    reference_gaps = [g for g in result.gaps if g.kind == "unresolved-precondition"]
    assert reference_gaps == []


def test_fixture_wiring_compiled_source_captures_before_it_is_consumed(tmp_path: Path) -> None:
    """`compile_plan` must not just credit `name` as produced — it has to emit the call that actually captures it, before the line that reads `$name` back."""
    packet, _base = _build(tmp_path, capture=True)
    source = compile_plan(packet, story="demo-story")
    assert 'qa.capture_field("name", observed_1.json(), "project.name")' in source
    capture_line = source.index('qa.capture_field("name"')
    verify_line = source.index('qa.verify("json_path"')
    assert capture_line < verify_line


def test_fixture_wiring_gaps_a_reference_with_no_producing_capture(tmp_path: Path) -> None:
    packet, _base = _build(tmp_path, capture=False)
    result = compile_plan_gaps(packet, story="demo-story")
    reference_gaps = [g for g in result.gaps if g.kind == "unresolved-precondition"]
    assert len(reference_gaps) == 1


def test_fixture_wiring_book_has_no_fixture_grammar_findings(tmp_path: Path) -> None:
    write(tmp_path / RUNBOOK_PATH, RUNBOOK)
    write(tmp_path / SEEDED_ACME_PATH, SEEDED_ACME)
    write(tmp_path / SEEDED_GLOBEX_PATH, SEEDED_GLOBEX)
    write(tmp_path / ENDPOINT_PATH, _endpoint_book(capture=True))

    findings = [f for f in doctor.run(load(tmp_path)).findings if f.code.startswith("fixture-")]
    assert findings == []


SEEDED_GLOBEX_WITH_NEEDS_ARG = """---
type: fixture
title: Seeded globex
---
# Seeded globex

- args: acme_id
- provides:
  - project_id — the seeded project's id
    - from: [seed-it](#seed-it)
    - read: project.id
- needs:
  - [seeded-acme](seeded-acme.md) acme_id=@seeded-acme.id

## Steps

### seed-it

- kind: seed
- run: ./scripts/seed-globex.sh --account $acme_id
"""


def test_fixture_wiring_needs_binding_checks_against_consumers_own_args(tmp_path: Path) -> None:
    """A `needs:` binding's names are the CONSUMER's own `args:`, never the target's."""
    write(tmp_path / RUNBOOK_PATH, RUNBOOK)
    write(tmp_path / SEEDED_ACME_PATH, SEEDED_ACME)
    write(tmp_path / SEEDED_GLOBEX_PATH, SEEDED_GLOBEX_WITH_NEEDS_ARG)
    write(tmp_path / ENDPOINT_PATH, _endpoint_book(capture=True))

    findings = [f for f in doctor.run(load(tmp_path)).findings if f.code.startswith("fixture-")]
    assert findings == []


def test_fixture_wiring_gaps_a_provided_fact_whose_source_the_book_leaves_open(
    tmp_path: Path,
) -> None:
    """End to end: strip one `from:`/`read:` pair and the obligations arranging it stop compiling."""
    _packet, base = _build(tmp_path, capture=True)
    write(tmp_path / SEEDED_ACME_PATH,
          SEEDED_ACME.replace("    - from: [seed-it](#seed-it)\n    - read: account.id\n", ""))
    packet = build_context(tmp_path, base=base, source_roots={"acme": ["app"]})

    result = compile_plan_gaps(packet, story="demo-story")

    undetermined = [g for g in result.gaps if g.kind == "undetermined-provided-fact"]
    assert undetermined, [g.kind for g in result.gaps]
    assert all("seeded-acme.id" in g.detail for g in undetermined)
