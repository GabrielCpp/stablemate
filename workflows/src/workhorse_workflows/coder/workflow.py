"""The `coder` distribution's composition root — nothing else."""
from __future__ import annotations

from workhorse.cli import console_script
from workhorse.pyflow import Registry
from workhorse_workflows.coder.docs import Docs
from workhorse_workflows.coder.fix import Fix
from workhorse_workflows.coder.fix_ci import FixCi
from workhorse_workflows.coder.genesis import Genesis
from workhorse_workflows.coder.dev import Dev
from workhorse_workflows.coder.main import Coder
from workhorse_workflows.coder.qa import Qa
from workhorse_workflows.coder.shared.blueprint import blueprint

workflow = (
    Registry("coder", package=__package__)
    .add_blueprints(blueprint)
    .add_flows(
        genesis=Genesis,
        dev=Dev,
        docs=Docs,
        qa=Qa,
        fix=Fix,
        fix_ci=FixCi,
    )
)
main = console_script(workflow.entry_point(Coder))


__all__ = ["Coder", "main", "workflow"]
