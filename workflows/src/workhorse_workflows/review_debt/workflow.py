"""`review-debt` — group the debt register's records by shared cause and write `trends.md`."""
from __future__ import annotations

from workhorse.cli import console_script
from workhorse.pyflow import Registry
from workhorse_workflows.review_debt.flow import ReviewDebt
from workhorse_workflows.review_debt.nodes import blueprint

workflow = (
    Registry("review-debt", package=__package__)
    .add_blueprints(blueprint)
)

main = console_script(workflow.entry_point(ReviewDebt))
