"""A scenario's context reaches its process whatever the book's size: the kernel caps one argument at 128 KiB."""

from __future__ import annotations

from pathlib import Path

from ostler.qa.drivers import PythonDriver
from ostler.qa.session import QaSession

from conftest import write

PLAN = '''\
from ostler_qa import Qa, plan, scenario, target

plan(run_id="qa-size", story="size")

api = target("api")


@scenario(target=api, mechanism="live", covers=["ac:1"])
def reads_its_context(qa: Qa) -> None:
    """The scenario starts."""
    qa.check("started", True)
'''


def test_a_context_larger_than_the_kernel_allows_one_argument_still_reaches_the_scenario(repo: Path) -> None:
    module = repo / "qa_plan.py"
    write(module, PLAN)
    spec = repo / "docs/specs/story-1"
    spec.mkdir(parents=True, exist_ok=True)
    session = QaSession.create(spec, "qa-size-1", "story-1", {})
    driver = PythonDriver(session, "api", {"driver": "python", "module": str(module)}, root=repo, variables={})
    context = {"root": str(repo), "spec_dir": str(spec), "qa_dir": str(session.qa_dir), "padding": "x" * 200_000}

    records, output, code, timed_out = driver.launcher.execute(driver, "reads-its-context", 60.0, context)

    assert (code, timed_out) == (0, False), output
    assert records[-1]["status"] == "passed"
