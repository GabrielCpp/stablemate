#!/usr/bin/env python3
"""Guard the declared-fixture rule across the benchmark corpus."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ostler.model import load
from ostler.qa.fixtures import declared, preflight_errors, referenced
from paddock import loader, paths
from workhorse_workflows.coder.shared.schemas.dev import lift_fixture


def _label(root: Path) -> str:
    """The benchmark's name for its `data/` repo, the repo's own name inside a folder of repos."""
    return root.parent.name if root.name == paths.DATA else root.name


def _check_app(root: Path) -> list[str]:
    """Every static fixture problem in one app tree."""
    spec_root = root / "docs" / "specs"
    if not spec_root.is_dir():
        return []

    problems = [f"{_label(root)}: {message}" for message in preflight_errors(root)]

    specs, _errors = declared(root)
    names = set(specs) | {Path(node.id).stem for node in load(root).ui_nodes_of_type("fixture")}
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


def main() -> int:
    root = paths.root()
    apps = loader.data_repos(root)
    if not apps:
        print(f"check-fixtures: no benchmark repos under {paths.gold_dir(root)}", file=sys.stderr)
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
