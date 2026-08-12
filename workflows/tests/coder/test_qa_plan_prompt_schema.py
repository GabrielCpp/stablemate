"""The `plan-qa` prompt's YAML example must satisfy the validator that judges its output.

`plan-qa` writes a `qa-plan.yml`, and `validate_qa_plan` runs `ostler qa validate` over it; an
`invalid` verdict routes the flow back to `plan` for another agent turn. So a schema rule the
prompt does not state is not a documentation gap — it is a guaranteed extra rework cycle on
*every* story, paid in wall-clock against the run's budget.

A live benchmark run spent one full re-plan (156s) on exactly two such rules, both of which the
example silently taught wrong:

  - `duplicate action id 'exercise'` (×5), `'assert-status'` (×5), `'gen-name'` (×2). Action ids
    are unique across the **whole plan** — `ostler/ostler/qa/plan.py` builds one `action_ids` set
    outside the scenario loop. The example's action was called `exercise`, so six scenarios
    written by analogy produced six `exercise`es. The example id is now prefixed with its
    scenario id so that copying it stays valid.
  - `action N must declare exactly one of do, expect, capture` (×9). The example only ever shows
    `do:`, and nothing said the three keys are alternatives rather than composable parts.

Both bullets name vocabulary — the `expect:` predicates and `capture:` kinds — that lives in
ostler, not here. Prose that lists another package's constants goes stale silently, so the sets
are checked against the real ones rather than restated and trusted.
"""
from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import yaml

import workhorse_workflows
from ostler.qa.plan import CAPTURES, EXPECTATIONS
from ostler.qa.session import QA_DIRNAME
from workhorse_workflows.coder.qa.flow import Qa
from workhorse_workflows.coder.qa.nodes.qa import QA_SCRATCH_DIRNAME

PROMPT = Path(workhorse_workflows.__file__).parent / "coder" / "prompts" / "plan-qa.md"

#: The fenced ```yaml block holding the plan skeleton the agent copies.
_YAML_BLOCK = re.compile(r"```yaml\n(.*?)```", re.DOTALL)


def _example_plan() -> dict:
    """The first ```yaml block in the prompt — the schema skeleton itself."""
    blocks = _YAML_BLOCK.findall(PROMPT.read_text())
    assert blocks, "plan-qa.md no longer carries a ```yaml example"
    return yaml.safe_load(blocks[0])


def _actions(plan: dict) -> list[tuple[str, dict]]:
    return [
        (scenario.get("id", "?"), action)
        for scenario in plan.get("scenarios", [])
        for action in scenario.get("actions", []) or []
    ]


def test_the_example_declares_exactly_one_of_do_expect_capture_per_action():
    """The rule the live run broke nine times. Checked on the example because the example is
    what the agent pattern-matches on — a prompt whose own YAML violated this would keep
    teaching the mistake no matter what the prose said."""
    for scenario_id, action in _actions(_example_plan()):
        keys = [key for key in ("do", "expect", "capture") if key in action]
        assert len(keys) == 1, f"scenario {scenario_id!r} action declares {keys}"


def test_example_action_ids_are_unique_and_scenario_prefixed():
    """Plan-global uniqueness is only survivable under copy-paste if the example's id carries
    its scenario id — an unqualified `exercise` becomes a duplicate the moment a second
    scenario is written the same way, which is precisely what happened."""
    seen: set[str] = set()
    for scenario_id, action in _actions(_example_plan()):
        action_id = action.get("id")
        assert action_id, f"scenario {scenario_id!r} has an action with no id"
        assert action_id not in seen, f"duplicate action id {action_id!r} in the example"
        seen.add(action_id)
        assert str(action_id).startswith(scenario_id), (
            f"action id {action_id!r} is not prefixed with its scenario id {scenario_id!r}; "
            "an agent copying it into a second scenario would emit a duplicate"
        )


#: The two prose clauses that enumerate ostler's vocabularies, e.g.
#: ``` `expect:` takes a UI predicate (`visible`, `hidden`, …) ```.
_VOCAB_CLAUSE = re.compile(r"`(expect|capture):` takes [^(]*\(([^)]*)\)", re.DOTALL)


def test_the_prose_names_only_predicates_ostler_actually_accepts():
    """The `expect:`/`capture:` bullet enumerates vocabularies that live in ostler, not here.
    Naming one ostler rejects would send the agent confidently into a validation error — the
    failure mode this whole file exists to prevent — and prose restating another package's
    constants goes stale with no signal at all."""
    clauses = _VOCAB_CLAUSE.findall(PROMPT.read_text())
    assert len(clauses) == 2, f"expected an expect: and a capture: clause, found {clauses}"

    real = {"expect": EXPECTATIONS, "capture": CAPTURES}
    for key, listed in clauses:
        named = set(re.findall(r"`([a-z_]+)`", listed))
        assert named, f"the {key}: clause lists no predicates"
        unknown = named - real[key]
        assert not unknown, f"plan-qa.md offers {key}: {sorted(unknown)}, which ostler rejects"


#: The two prompts `Qa._plan_args` renders. Both are fed from that one dict, so a name
#: either of them reads has to be a key in it.
PLAN_PROMPTS = (PROMPT, PROMPT.parent / "repair-qa-plan.md")

#: `{{ workhorse_var('x') }}` for the scalars, and the bare `{% if x %}` / `{% for … in x %}`
#: form the structured arguments use — `qa_stack`, `shared_packages`.
_SCALAR_ARG = re.compile(r"workhorse_var\(\s*'([a-z_]+)'\s*\)")
_STRUCTURED_ARG = re.compile(r"{%-?\s*(?:if|for\s+\w+\s+in)\s+([a-z_]+)(?![a-z_(])")


def _plan_arg_keys() -> set[str]:
    """The literal keys of the dict `_plan_args` returns, read from its source.

    Read statically rather than by calling it: the method needs a live flow with a resolved
    `ImplContext` behind it, and what this test is guarding is the much smaller claim that a
    name a prompt interpolates is a name the flow passes."""
    tree = ast.parse(inspect.getsource(Qa._plan_args).lstrip())
    returns = [n for n in ast.walk(tree) if isinstance(n, ast.Return)]
    assert len(returns) == 1, "_plan_args no longer ends in a single return"
    literal = returns[0].value
    assert isinstance(literal, ast.Dict), "_plan_args no longer returns a dict literal"
    return {k.value for k in literal.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}


def test_the_plan_prompts_only_interpolate_arguments_the_flow_passes():
    """A misspelled name renders as empty and says nothing — Jinja has no undefined error
    here — so the prompt silently loses the brief it was supposed to carry. That is how
    `plan-context.json` reached one prompt for months while `plan-qa.md` described it in
    prose."""
    keys = _plan_arg_keys()
    #: Jinja's own names and the loop variables the templates bind themselves.
    local = {"raw", "endraw", "repo", "f", "p", "r"}
    for prompt in PLAN_PROMPTS:
        text = prompt.read_text()
        named = set(_SCALAR_ARG.findall(text)) | set(_STRUCTURED_ARG.findall(text))
        unknown = named - keys - local
        assert not unknown, f"{prompt.name} reads {sorted(unknown)}, which _plan_args omits"


def test_the_dry_run_scratch_directory_is_not_the_evidence_directory():
    """The whole separation: a scenario tuned until it passed must not be able to write into
    the ledger `verify_qa_evidence` reads."""
    assert QA_SCRATCH_DIRNAME != QA_DIRNAME
    for prompt in PLAN_PROMPTS:
        text = prompt.read_text()
        assert "--out-dir" in text, f"{prompt.name} does not teach the dry run"
        assert "qa_scratch_dir" in text, f"{prompt.name} hard-codes the dry-run directory"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
