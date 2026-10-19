"""`scenario_covers` reads which book ids each scenario of a plan claims, without running the plan."""
from __future__ import annotations

from pathlib import Path

from ostler.qa.plan import scenario_covers

PAGE = "okf:docs/features/api/http/get-thing.md"

PLAN = f'''
from ostler_qa import Qa, plan, scenario, target

api = target("api")


@scenario(target=api, mechanism="live", covers=["{PAGE}:contract"], id="reads-thing")
def reads_thing(qa: Qa) -> None:
    qa.check("it answers", True, covers=["{PAGE}:contract", "{PAGE}:emits:1"])


@scenario(target=api, mechanism="live", covers=[])
def lists_things(qa: Qa) -> None:
    qa.require("it lists", True, covers=["okf:docs/features/api/http/list-things.md:contract"])


@scenario(target=api, mechanism="live", covers=COMPUTED_IDS)
def computed(qa: Qa) -> None:
    qa.check("it computes", True)
'''


def test_scenario_level_and_per_check_ids_are_both_collected(tmp_path: Path) -> None:
    plan_file = tmp_path / "qa_plan.py"
    plan_file.write_text(PLAN, encoding="utf-8")

    found = scenario_covers(plan_file)

    assert found["reads-thing"] == [f"{PAGE}:contract", f"{PAGE}:emits:1"]
    assert found["lists-things"] == ["okf:docs/features/api/http/list-things.md:contract"]
    assert found["computed"] == []


def test_a_missing_or_broken_plan_covers_nothing(tmp_path: Path) -> None:
    broken = tmp_path / "qa_plan.py"
    broken.write_text("def (:\n", encoding="utf-8")

    assert scenario_covers(tmp_path / "absent.py") == {}
    assert scenario_covers(broken) == {}
