#!/usr/bin/env python3
"""Guard the declared-fixture rule across the benchmark corpus. Wired into `make test`.

A QA fixture is held to the bar a test is held to: it is named, it is declared, and the
declaration is what admits it. `ostler qa lint` already enforces the import half — a plan
may import `_fixtures.<name>` only for a name in `agents.yml`'s `qa: {fixture_modules:}`
— and `ostler.qa.fixtures.preflight_errors` already enforces the declaration half at the
top of a run. Both are per-run, per-plan checks, and that is exactly what leaves a gap.

The three failures below are all invisible to a run:

- **A fixture module on disk that nobody declared.** Every plan importing it was deleted
  or repointed, so no lint pass ever reads its name, and the file sits there looking like
  shared code while being unreachable. The next author copies from it.
- **A declaration with no file behind it**, or one naming a tool the repo never opted
  into. `preflight_errors` catches these — but only for the app a run happens to be
  materializing. Four of the five corpus apps are untouched by any given round.
- **A plan calling `qa.fixture("name")` for a name no `qa: {fixtures:}` entry declares.**
  This one *does* fail the run, at the moment the scenario reaches for it — which is
  after the app booted, and reported as a blocked scenario rather than as the typo it is.

The corpus is where this bites hardest: its plans are frozen, most rounds spend zero
agent turns, and a benchmark app is only ever exercised by the one task that names it. A
drifted fixture declaration in `seat-booking` can sit unnoticed for as long as nobody
runs `seat-booking-qa`.

This guard is a static sweep and claims nothing beyond it. It does not run a fixture, does
not check that `provides:` is true, and does not check that a scenario's preconditions are
the ones its fixtures guarantee — those need the run, not a grep.

Run:
    uv run --all-packages python scripts/check_fixtures.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from ostler.qa.fixtures import FIXTURES_DIRNAME, declared, declared_modules, preflight_errors

#: Where the benchmark apps live. The only trees in this repo that carry QA plans at all:
#: stablemate's own code is tested with pytest, not with an OKF QA lane.
CORPUS = Path(__file__).resolve().parent.parent / "paddock" / "data" / "apps"


def _fixture_names_called(plan: Path) -> set[str]:
    """Every literal name a plan hands to `qa.fixture(...)`.

    Read off the AST rather than by grep, for the same reason `covers=` is: a name built
    at runtime claims nothing a static check could have verified, and this pass would
    rather see none than see a fragment of one.
    """
    try:
        tree = ast.parse(plan.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        # Not this guard's finding: `ostler qa lint` and ruff both fail on it first, and
        # reporting it twice in two vocabularies helps nobody.
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "fixture"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            names.add(node.args[0].value)
    return names


def _check_app(root: Path) -> list[str]:
    """Every static fixture problem in one app tree."""
    spec_root = root / "docs" / "specs"
    if not spec_root.is_dir():
        return []

    problems = [f"{root.name}: {message}" for message in preflight_errors(root, spec_root=spec_root)]

    modules = declared_modules(root)
    directory = spec_root / FIXTURES_DIRNAME
    if directory.is_dir():
        problems.extend(
            f"{root.name}: {FIXTURES_DIRNAME}/{path.name} is not declared — add "
            f"{path.stem!r} to agents.yml's `qa: {{fixture_modules: [...]}}`, or delete it. "
            "An undeclared module is unreachable: no plan may import it."
            for path in sorted(directory.glob("*.py"))
            if path.stem not in modules and path.name != "__init__.py"
        )

    specs, _errors = declared(root)
    for plan in sorted(spec_root.glob("*/qa_plan.py")):
        story = plan.parent.name
        known = ", ".join(sorted(specs)) or "(none declared)"
        problems.extend(
            f"{root.name}/{story}: `qa.fixture({name!r})` names a fixture this repo has "
            f"not declared. Declared here: {known}"
            for name in sorted(_fixture_names_called(plan))
            if name not in specs
        )
    return problems


def main() -> int:
    apps = sorted(path for path in CORPUS.iterdir() if path.is_dir()) if CORPUS.is_dir() else []
    if not apps:
        # A guard that finds nothing to guard has failed, not passed: the corpus moved and
        # this check would go on reporting clean for every app it can no longer see.
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
