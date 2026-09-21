#!/usr/bin/env python3
"""Guard the declared-fixture rule across the benchmark corpus."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ostler.qa.fixtures import declared, preflight_errors, referenced
from workhorse_workflows.coder.shared.schemas.dev import lift_fixture

CORPUS = Path(__file__).resolve().parent.parent / "paddock" / "data" / "apps"


def _check_app(root: Path) -> list[str]:
    """Every static fixture problem in one app tree."""
    spec_root = root / "docs" / "specs"
    if not spec_root.is_dir():
        return []

    problems = [f"{root.name}: {message}" for message in preflight_errors(root)]

    specs, _errors = declared(root)
    problems.extend(_story_declaration_problems(root, spec_root, specs))
    for plan in sorted(spec_root.glob("*/qa_plan.py")):
        story = plan.parent.name
        known = ", ".join(sorted(specs)) or "(none declared)"
        problems.extend(
            f"{root.name}/{story}: `qa.fixture({name!r})` names a fixture this repo has "
            f"not declared. Declared here: {known}"
            for name in sorted(referenced(plan))
            if name not in specs
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


def _story_declaration_problems(root: Path, spec_root: Path, specs: dict) -> list[str]:
    """Every story that names a fixture the repo never declared."""
    problems = []
    for document_path in sorted(spec_root.glob("*/plan-context.json")):
        try:
            document = json.loads(document_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append(f"{root.name}/{document_path.parent.name}: unreadable plan-context.json ({exc})")
            continue
        if not isinstance(document, dict):
            continue
        known = ", ".join(sorted(specs)) or "(none declared)"
        problems.extend(
            f"{root.name}/{document_path.parent.name}: the story declares fixture "
            f"{name!r}, which this repo has not declared. Declared here: {known}"
            for name in _story_fixture_names(document)
            if name not in specs
        )
    return problems


def main() -> int:
    apps = sorted(path for path in CORPUS.iterdir() if path.is_dir()) if CORPUS.is_dir() else []
    if not apps:
        print(f"check-fixtures: no benchmark apps under {CORPUS}", file=sys.stderr)
        return 1

    problems = [problem for app in apps for problem in _check_app(app)]
    if problems:
        print("check-fixtures: declared-fixture rule violated\n", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    print(f"ok: fixture declarations agree with the tree in {len(apps)} benchmark apps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
