"""The `coder` distribution's composition root — nothing else."""
from __future__ import annotations

from workhorse.cli import console_script
from workhorse.pyflow import Registry
from workhorse_workflows.coder.dev import Dev
from workhorse_workflows.coder.docs import Docs
from workhorse_workflows.coder.fix import Fix
from workhorse_workflows.coder.fix_ci import FixCi
from workhorse_workflows.coder.genesis import Genesis
from workhorse_workflows.coder.main import Coder
from workhorse_workflows.coder.qa import Qa
from workhorse_workflows.coder.review import Review
from workhorse_workflows.coder.shared.blueprint import blueprint

workflow = (
    Registry("coder", package=__package__)
    .add_blueprints(blueprint)
    .add_flows(
        genesis=Genesis,
        dev=Dev,
        review=Review,
        docs=Docs,
        qa=Qa,
        fix=Fix,
        fix_ci=FixCi,
    )
    .stub_agents(
        {
            "plan-story": {"status": "complete"},
            "repair-plan-paths": {"status": "done"},
            "replan-with-answer": {"status": "done"},
            "implement-plan": {"status": "complete"},
            "dev-fix": {"status": "fixed"},
            "code-review": {"status": "clean"},
            "review-implementation": {"status": "approved"},
            "apply-review": {"status": "applied"},
            "document-story": {"status": "passed"},
            "review-story-documentation": {"status": "passed"},
            "plan-qa": {"status": "complete"},
            "qa-story": {"status": "passed"},
            "audit-qa": {"status": "passed"},
            "apply-qa-fixes": {"status": "passed"},
            "triage-qa": {"status": "resolved"},
            "repair-qa-context": {"status": "repaired"},
            "report-qa-dev": {"status": "reported"},
            "report-qa-dev-pass": {"status": "reported"},
            "fix-regression": {"status": "fixed"},
            "setup-fix": {"status": "fixed"},
            "fix-ci": {"status": "fixed"},
            "fix-merge": {"status": "resolved"},
            "replan-epic": {"status": "complete"},
            "resolve-operator": {"decision": "answered"},
        }
    )
)
main = console_script(workflow.entry_point(Coder))


__all__ = ["Coder", "main", "workflow"]
