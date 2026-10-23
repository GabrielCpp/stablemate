"""The trends file: a deterministic rendering of a report that passed accounting."""
from __future__ import annotations

import logging
from pathlib import Path

from ostler import Ostler, register
from workhorse_workflows.kit import find_docs_root
from workhorse_workflows.review_debt.nodes._blueprint import blueprint
from workhorse_workflows.review_debt.schemas import CompleteRead, TrendReport, TrendsWritten

TRENDS_FILE = "trends.md"
COMMIT_MESSAGE = "chore: review the debt register"


def _line(entries: dict[str, list[str]], record_id: str, text: str) -> str:
    """One `- id (repo/area, status): summary` bullet; the cause closes it when *text* is set."""
    repo, area, status, summary = entries[record_id]
    line = f"- {record_id} ({repo}/{area}, {status}): {summary}"
    return f"{line} (cause: {_flat(text)})" if text else line


def _flat(text: str) -> str:
    """*text* on one line, so no model prose can start a line with `- `."""
    return " ".join(text.split())


def render(read: CompleteRead, report: TrendReport) -> str:
    """The text of `trends.md` for *report* over *read*."""
    entries: dict[str, list[str]] = {}
    for row in read.listing:
        record_id, repo, area, status, _pattern, summary = row.split("\t", 5)
        entries[record_id] = [repo, area, status, summary]
    order = {record_id: n for n, record_id in enumerate(read.ids)}
    out = ["# Debt register trends", "", f"{len(read.ids)} records reviewed", "", _flat(report.summary), ""]
    for cluster in report.clusters:
        out += [f"## {_flat(cluster.name)}", "", _flat(cluster.cause), ""]
        out += [_line(entries, i, "") for i in sorted(cluster.ids, key=order.__getitem__)]
        out.append("")
    if report.singletons:
        out += ["## Singletons", ""]
        out += [_line(entries, s.id, s.cause) for s in sorted(report.singletons, key=lambda s: order[s.id])]
        out.append("")
    return "\n".join(out)


@blueprint.node
def write_trends(
    logger: logging.Logger, read: CompleteRead, report: TrendReport, repo_dir: str = ""
) -> TrendsWritten:
    """Write `trends.md` beside the shelf and commit that one file in the artifacts repo; a rewrite of the same text commits nothing."""
    okf = Ostler(find_docs_root(repo_dir))
    target = Path(read.shelf) / TRENDS_FILE
    target.write_text(render(read, report), encoding="utf-8")
    committed = register.commit(okf.graph, [target], COMMIT_MESSAGE)
    logger.info("trends.md %s", "committed" if committed else "unchanged")
    return TrendsWritten(path=str(target), committed=committed)
