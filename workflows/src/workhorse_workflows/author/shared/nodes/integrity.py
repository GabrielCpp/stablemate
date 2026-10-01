"""`ostler doctor` over the planning graph, as a blocking gate."""
from __future__ import annotations

import logging

from ostler import Ostler
from workhorse_workflows.author.shared.nodes.blueprint import blueprint
from workhorse_workflows.author.shared.nodes import stubs as _stubs
from workhorse_workflows.author.shared.paths import launch_repo_root
from workhorse_workflows.author.shared.schemas.main import VerifyReport


@blueprint.node(stub=_stubs.holds)
def verify_integrity(
    logger: logging.Logger,
    epic: str = "",
    repo_dir: str = "",
) -> VerifyReport:
    """`ostler doctor` over the whole graph, as a blocking gate."""
    okf = Ostler(launch_repo_root(repo_dir))

    outcome = okf.doctor(epic=epic.strip() or None)
    if outcome.status == "invalid":
        logger.warning("%s — skipped", outcome.message)
        return VerifyReport(skipped=True, report=f"{outcome.message} — skipped")

    report = outcome.data
    findings = report.get("findings", [])
    errors = [f for f in findings if f.get("severity") == "error"]
    warns = [f for f in findings if f.get("severity") == "warn"]
    summary = (
        f"ostler doctor [{report.get('org', '?')}/{report.get('profile', '?')}]: "
        f"{len(errors)} error(s), {len(warns)} warning(s)"
    )
    logger.info(summary)

    if not errors:
        return VerifyReport(holds=True, report=summary)

    lines = [
        "ostler doctor found referential-integrity errors in the planning-doc graph.",
        "Each is a graph break (a reference that resolves to nothing, or to the wrong epic).",
        "Reconcile each with `ostler edit` (relink / rename) or escalate — never",
        "delete a reference or fabricate an entity to silence the check.",
        "",
    ]
    for f in errors:
        scope = f.get("epic") or f.get("ref") or ""
        scope = f" ({scope})" if scope else ""
        lines.append(f"  - [{f.get('code', '?')}]{scope} {f.get('message', '')}")
    return VerifyReport(errors="\n".join(lines), report=summary)


__all__ = ["verify_integrity"]
