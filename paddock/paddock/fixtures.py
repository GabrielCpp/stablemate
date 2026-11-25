"""Static fixture checks on a benchmark's app trees: what a run would otherwise find out after spending turns."""

from __future__ import annotations

import json
from pathlib import Path

from ostler.qa.fixtures import declared, preflight_errors, referenced
from workhorse_workflows.coder.shared.schemas.dev import lift_fixture

from paddock import loader, paths


def _label(root: Path) -> str:
    """The benchmark's name for its `data/` repo, the repo's own name inside a folder of repos."""
    return root.parent.name if root.name == paths.DATA else root.name


def check_app(root: Path) -> list[str]:
    """Every static fixture problem in one app tree."""
    spec_root = root / "docs" / "specs"
    if not spec_root.is_dir():
        return []

    problems = [f"{_label(root)}: {message}" for message in preflight_errors(root)]

    specs, _errors = declared(root)
    names = set(specs)
    problems.extend(_story_declaration_problems(root, spec_root, names))
    for plan in sorted(spec_root.glob("*/qa_plan.py")):
        story = plan.parent.name
        known = ", ".join(sorted(names)) or "(none declared)"
        problems.extend(
            f"{_label(root)}/{story}: `qa.fixture({name!r})` names a fixture this repo has "
            f"not declared. Declared here: {known}"
            for name in sorted(referenced(plan))
            if name not in names
        )
    return problems


def _story_fixture_names(document: dict) -> list[str]:
    """The fixture *names* a `plan-context.json` declares, under either spelling."""
    raw = document.get("fixtures")
    if not isinstance(raw, list):
        setup = document.get("verification_setup") or document.get("qa_stack") or {}
        raw = setup.get("fixtures") if isinstance(setup, dict) else None
    if not isinstance(raw, list):
        return []
    names = []
    for item in raw:
        name = lift_fixture(item).get("name") if isinstance(item, str) else None
        if isinstance(item, dict):
            name = str(item.get("name") or "")
        if name:
            names.append(name)
    return names


def _story_declaration_problems(root: Path, spec_root: Path, names: set[str]) -> list[str]:
    """Every story that names a fixture the repo never declared."""
    problems = []
    for document_path in sorted(spec_root.glob("*/plan-context.json")):
        try:
            document = json.loads(document_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append(f"{_label(root)}/{document_path.parent.name}: unreadable plan-context.json ({exc})")
            continue
        if not isinstance(document, dict):
            continue
        known = ", ".join(sorted(names)) or "(none declared)"
        problems.extend(
            f"{_label(root)}/{document_path.parent.name}: the story declares fixture "
            f"{name!r}, which this repo has not declared. Declared here: {known}"
            for name in _story_fixture_names(document)
            if name not in names
        )
    return problems


def benchmark_problems(root: Path, benchmark: str) -> list[str]:
    """Every static fixture problem in the repos of one benchmark."""
    return [problem for repo in loader.benchmark_repos(root, benchmark) for problem in check_app(repo)]
