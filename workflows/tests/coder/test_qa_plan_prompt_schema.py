"""The `plan-qa` prompt's python example must be a plan the harness would actually accept."""
from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import workhorse_workflows
from ostler.qa.harness import ostler_qa as harness
from ostler.qa.session import QA_DIRNAME
from workhorse_workflows.coder.qa.flow import Qa
from workhorse_workflows.coder.qa.nodes.qa import QA_SCRATCH_DIRNAME

PROMPT = (
    Path(workhorse_workflows.__file__).parent / "coder" / "qa" / "prompts" / "plan-qa.md"
)

_PYTHON_BLOCK = re.compile(r"```python\n(.*?)```", re.DOTALL)


def _example_source() -> str:
    """The first ```python block in the prompt — the plan skeleton itself."""
    blocks = _PYTHON_BLOCK.findall(PROMPT.read_text())
    assert blocks, "plan-qa.md no longer carries a ```python example"
    return blocks[0]


def _example_tree() -> ast.Module:
    return ast.parse(_example_source())


def test_the_example_is_valid_python():
    """An example that does not parse teaches a plan that does not import, and an unimportable plan now fails validation outright rather than an hour later as a driver failure."""
    _example_tree()


def test_the_example_imports_only_names_the_harness_exports():
    """`ostler_qa` is ostler's, not this package's."""
    imported = {
        alias.name
        for node in ast.walk(_example_tree())
        if isinstance(node, ast.ImportFrom) and node.module == "ostler_qa"
        for alias in node.names
    }
    assert imported, "the example no longer imports from ostler_qa"
    unknown = imported - set(harness.__all__)
    assert not unknown, f"plan-qa.md imports {sorted(unknown)}, which ostler_qa does not export"


def _qa_attributes() -> set[str]:
    """Everything a scenario may reach through `qa`: the class's own methods and properties, plus the instance attributes `__init__` binds — `qa.http` and `qa.diagnostics` exist only as assignments, so `dir(Qa)` alone would call them invented."""
    tree = ast.parse(inspect.getsource(harness.Qa).lstrip())
    bound = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.ctx, ast.Store)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    }
    return bound | set(dir(harness.Qa))


def test_the_example_only_calls_qa_attributes_that_exist():
    """Every affordance the example demonstrates is an attribute of the `Qa` the harness hands the scenario."""
    used = {
        node.value.attr if isinstance(node.value, ast.Attribute) else node.attr
        for node in ast.walk(_example_tree())
        if isinstance(node, ast.Attribute)
        and (
            (isinstance(node.value, ast.Name) and node.value.id == "qa")
            or (
                isinstance(node.value, ast.Attribute)
                and isinstance(node.value.value, ast.Name)
                and node.value.value.id == "qa"
            )
        )
    }
    assert used, "the example no longer touches `qa`"
    unknown = used - _qa_attributes()
    assert not unknown, f"plan-qa.md calls qa.{sorted(unknown)}, which the harness does not have"


def test_the_example_scenario_would_survive_the_substantiveness_gate():
    """`ostler qa validate` refuses a scenario that claims coverage and calls no `qa.check`, counted from the source by `count_checks`."""
    counts = harness.count_checks(_example_source())
    assert counts, "the example declares no scenario `count_checks` can see"
    for scenario_id, count in counts.items():
        assert count > 0, f"example scenario {scenario_id!r} records no assertion"


def test_the_prose_names_only_mechanisms_and_drivers_ostler_accepts():
    """`mechanism` and `driver` are ostler's vocabularies."""
    text = PROMPT.read_text()
    for label, vocabulary in (("mechanism", harness.MECHANISMS), ("driver", harness.DRIVER_NAMES)):
        clause = re.search(rf"`{label}` is \w+ \(([^)]*)\)", text)
        assert clause, f"plan-qa.md no longer enumerates the {label} vocabulary"
        named = set(re.findall(r"`([a-z_]+)`", clause.group(1)))
        assert named, f"the {label} clause lists nothing"
        unknown = named - set(vocabulary)
        assert not unknown, f"plan-qa.md offers {label} {sorted(unknown)}, which ostler rejects"


PLAN_PROMPTS = (PROMPT, PROMPT.parent / "repair-qa-plan.md")

_SCALAR_ARG = re.compile(r"workhorse_var\(\s*'([a-z_]+)'\s*\)")
_STRUCTURED_ARG = re.compile(r"{%-?\s*(?:if|for\s+\w+\s+in)\s+([a-z_]+)(?![a-z_(])")


def _plan_arg_keys() -> set[str]:
    """The literal keys of the dict `_plan_args` returns, read from its source."""
    tree = ast.parse(inspect.getsource(Qa._plan_args).lstrip())
    returns = [n for n in ast.walk(tree) if isinstance(n, ast.Return)]
    assert len(returns) == 1, "_plan_args no longer ends in a single return"
    literal = returns[0].value
    assert isinstance(literal, ast.Dict), "_plan_args no longer returns a dict literal"
    return {k.value for k in literal.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}


def test_the_plan_prompts_only_interpolate_arguments_the_flow_passes():
    """A misspelled name renders as empty and says nothing — Jinja has no undefined error here — so the prompt silently loses the brief it was supposed to carry."""
    keys = _plan_arg_keys()
    local = {"raw", "endraw", "repo", "f", "p", "r", "scenario"}
    for prompt in PLAN_PROMPTS:
        text = prompt.read_text()
        named = set(_SCALAR_ARG.findall(text)) | set(_STRUCTURED_ARG.findall(text))
        unknown = named - keys - local
        assert not unknown, f"{prompt.name} reads {sorted(unknown)}, which _plan_args omits"


def test_the_dry_run_scratch_directory_nests_inside_the_ignored_one():
    """Scratch is a subdirectory of the ledger directory, not a sibling of it."""
    assert QA_SCRATCH_DIRNAME == QA_DIRNAME
    for prompt in PLAN_PROMPTS:
        text = prompt.read_text()
        assert "--out-dir" in text, f"{prompt.name} does not teach the dry run"
        assert "qa_scratch_dir" in text, f"{prompt.name} hard-codes the dry-run directory"


def test_no_prompt_passes_a_path_to_out_dir():
    """`--out-dir` is one label now, and ostler refuses anything with a separator in it."""
    for prompt in PLAN_PROMPTS:
        for line in prompt.read_text().splitlines():
            match = re.search(r"--out-dir\s+(\S+)", line)
            if match is None:
                continue
            argument = match.group(1)
            assert "/" not in argument, f"{prompt.name} passes a path to --out-dir: {argument}"


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
