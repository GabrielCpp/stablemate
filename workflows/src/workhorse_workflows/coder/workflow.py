"""The `coder` distribution's composition root — nothing else.

`workhorse-coder` is bound here (`workflows/pyproject.toml`), and this module is what the
script imports: the registry that names the distribution, folds in its node blueprint,
lists the flows a caller can run by name, and declares what a `--dry-run` gets back from
each prompt. The graph a bare `run` starts is a flow package like the other eight —
[`main/`](main) — so the nine sit side by side and this file stays a table of contents.

The registry declares its own `package`, and that is load-bearing rather than tidy: it is
the root every prompt path renders against (`dev/prompts/implement-plan.md`) and the name
the repo-flavor lookup uses (`.agents/flavors/coder/`). Inferred from the entry class
instead, both would follow `Coder` into `main/` and every sibling flow's prompts would fall
outside the loader.
"""
from __future__ import annotations

from workhorse.cli import console_script
from workhorse.pyflow import Registry
from workhorse_workflows.coder.dev import Dev
from workhorse_workflows.coder.docs import Docs
from workhorse_workflows.coder.dream import Dream
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
    # The eight registered Python sub-flows, by the name `workhorse-coder run <name>`
    # takes. Five are reached by `handoff`; `genesis`, `dream` and `fix` are entered
    # directly.
    .add_flows(
        genesis=Genesis,
        dev=Dev,
        review=Review,
        docs=Docs,
        qa=Qa,
        fix=Fix,
        fix_ci=FixCi,
        dream=Dream,
    )
    .stub_agents(
        {
            # Keyed by prompt STEM: the reply that makes a dry run *progress* past each
            # gate rather than taking the pessimistic blank arm.
            "plan-story": {"status": "complete"},
            "refine-plan": {"status": "complete"},
            "implement-plan": {"status": "complete"},
            "dev-fix": {"status": "fixed"},
            "code-review": {"status": "approved"},
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
            "dream-reflect": {"status": "complete"},
        }
    )
)
main = console_script(workflow.entry_point(Coder))


__all__ = ["Coder", "main", "workflow"]
