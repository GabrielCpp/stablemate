"""Family-neutral QA domain code: bring a stack up, run a plan, verify its evidence.

A sibling of `kit` rather than a member of it — this is QA domain logic, not
infrastructure. `coder.qa.nodes` wraps `runner.ensure_stack`/`runner.run_qa_plan` and
`evidence.verify_qa_evidence` as `@blueprint.node`s; any other family calls the same
plain functions directly.
"""
from __future__ import annotations
