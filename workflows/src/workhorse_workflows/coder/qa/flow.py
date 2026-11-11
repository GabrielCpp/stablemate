"""One QA owner selects, runs, debugs and records a story's QA, and the run checks it."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, ClassVar

from ostler.qa.compile import compiled_from_the_book
from workhorse.pyflow import Await, Continue, Done, WorkflowFailed

from workhorse_workflows.kit import find_docs_root
from workhorse_workflows.coder.book_qa.nodes import defer_book_judged, read_book_record
from workhorse_workflows.coder.qa.nodes import (
    QA_SCRATCH_DIRNAME,
    check_sentinel_ids,
    clear_qa_evidence,
    compile_story_plan,
    detect_regression_suites,
    ensure_stack,
    flush_root_screenshots,
    lint_qa_plan,
    qa_tools_catalog,
    run_qa_plan,
    run_regression_suite,
    stack_target,
    validate_qa_plan,
    verify_qa_evidence,
)
from workhorse_workflows.coder.shared.qa_support import QA_COMPILED_PLAN_FILE, QA_PLAN_FILE
from workhorse_workflows.coder.qa.report import (
    book_failure,
    environment_failure,
    failed_scenarios_arg,
    fallback_finding,
    gate_text,
    product_findings,
    qa_only_arg,
    refix_findings,
    regression_text,
    stack_failures,
    unclassified_failure,
    unfinished_run,
    unproved_findings,
)
from workhorse_workflows.coder.qa.sides import run_sides
from workhorse_workflows.coder.shared import causes, roles
from workhorse_workflows.coder.shared.backlog import (
    file_backlog_items,
    file_deferred_obligations,
    filed_backlog,
    unfiled,
)
from workhorse_workflows.coder.book_qa.nodes import covered_services, without_covered_roots
from workhorse_workflows.coder.shared.docs import CONTEXT_FILE, detect_okf_docs, services_root
from workhorse_workflows.coder.shared.okf import TRUNK, build_okf_context, validate_okf_context
from workhorse_workflows.coder.shared.plan import plan_summary, resolve_impl_context
from workhorse_workflows.coder.shared.qa_owner import QaOwner
from workhorse_workflows.coder.shared.provenance import resolve_story_sources
from workhorse_workflows.coder.shared.reach import resolve_check_set
from workhorse_workflows.coder.shared.review import check_feedback
from workhorse_workflows.coder.shared.schemas.qa import (
    QaFinding,
    QaFlowResult,
    QaFlowStatus,
    QaOwnerResult,
    QaPlanRun,
    QaResult,
)
from workhorse_workflows.coder.shared.story import (
    stamp_specs,
    sync_story_fixtures,
)
from workhorse_workflows.coder.shared.worktree import code_changed, snapshot_code_state
from workhorse_workflows.kit.credentials import scoped_envs
from workhorse_workflows.kit.qa.runner import copy_lease


JUDGED_NOTE = "every obligation of this story was judged by a service book"


class Qa(QaOwner):
    """QA one story through one owner session, then rerun and gate what it claims."""

    stop_at_first_verdict: bool = False
    rerun: bool = False
    scope: tuple[str, ...] = ()

    LABEL_PREFIX: ClassVar[str] = "qa"

    def _file_backlog(self) -> None:
        """File the items the owner left for the backlog, less the ones an open `qa` record already holds."""
        pending = self.call(filed_backlog, self.ctx.spec_dir)
        keep = set(unfiled(causes.cause_judge(self, "low"), self.logger, pending.items, pending.filed))
        drop = [item_id for item_id in pending.items if item_id not in keep]
        self.call(file_backlog_items, self.ctx.spec_dir, drop=drop)

    def start(self) -> Continue | Done:
        """Clear the last run's evidence, decode what the story touched, and check its context and stack."""
        self.call(snapshot_code_state)
        if not (self.rerun and self.scope):
            self.call(clear_qa_evidence, self.ctx.spec_dir)
        impl = self.call(resolve_impl_context, self.ctx.spec_dir)
        if self._sourced:
            sources = self.call(
                resolve_story_sources,
                tuple(impl.dispatch_list),
                self.ctx.story_slug,
                self.ctx.story_id,
            )
            if sources.status != "valid":
                raise WorkflowFailed(
                    "story source provenance could not be resolved: " + "; ".join(sources.errors)
                )
        okf = self.call(detect_okf_docs)
        lease = copy_lease(self.ctx.story_id or self.ctx.story_slug, self.run_id)
        self.call(stack_target, self.ctx.story_slug, lease)
        if self.rerun:
            return Continue(okf, self.recheck)
        failures = self._preflight()
        if self._all_judged_by_books():
            return self._finish_judged()
        return Continue(okf, self.work, report="\n\n".join(failures))

    def _all_judged_by_books(self) -> bool:
        """Does a clean book record name services, hold no unreached claim, and leave the packet no required obligation undeferred?"""
        if self.output(validate_okf_context).status != "passed":
            return False
        record = self.call(read_book_record, self.ctx.spec_dir)
        if not record.services or record.findings or record.unreached:
            return False
        context = Path(self.ctx.spec_dir) / CONTEXT_FILE
        if not context.is_file():
            return False
        obligations = json.loads(context.read_text(encoding="utf-8")).get("obligations") or []
        return not any(
            isinstance(o, dict) and o.get("required", True) is not False and not isinstance(o.get("deferred"), dict)
            for o in obligations
        )

    def _finish_judged(self) -> Done:
        """Pass a story whose every obligation a service book judged, with no seat turn and no plan."""
        self.logger.info("QA passed for %s without a plan: its books judged it", self.ctx.story_slug)
        return self._finish("passed", QaPlanRun(status="passed", notes=JUDGED_NOTE))

    @property
    def _sourced(self) -> bool:
        return bool(self.workspace and self.ctx.story_id)

    def _preflight(self) -> list[str]:
        """The OKF context packet and the QA stack, as failures the owner repairs."""
        impl = self.output(resolve_impl_context)
        self.call(defer_book_judged, self.ctx.spec_dir)
        covered = self.call(covered_services, list(self.ctx.story_services)).services
        book_only = bool(covered) and len(covered) == len(set(self.ctx.story_services))
        build = self.call(
            build_okf_context,
            self.ctx.spec_dir,
            self.ctx.story_path,
            services_root(self),
            without_covered_roots(tuple(impl.qa_source_roots), covered)
            if covered and not book_only
            else tuple(impl.qa_source_roots),
            TRUNK,
            "WORKTREE",
            preexisting=tuple(self.preexisting),
            story_sources=self.output(resolve_story_sources).sources if self._sourced else (),
            story_refs=tuple(
                dict.fromkeys(ref for ref in (self.ctx.story_id, self.ctx.story_slug) if ref)
            ),
            book_only=book_only,
        )
        context =self.call(validate_okf_context, self.ctx.spec_dir, build.status)
        failures = []
        if context.status != "passed":
            failures.append(gate_text("the OKF context packet", context.notes))
        else:
            self.call(compile_story_plan, self.ctx.spec_dir, self.ctx.story_id or self.ctx.story_slug)
        target = self.output(stack_target)
        stack = self.call(ensure_stack, near=target.near, lease=target.lease)
        return failures + stack_failures(stack)

    def _owner_args(self) -> dict[str, Any]:
        """What the owner reads about its story, its plan and the tools it may drive."""
        impl = self.output(resolve_impl_context)
        reach = self.call(
            resolve_check_set,
            tuple(impl.dispatch_list),
            self.ctx.story_slug,
            self.ctx.story_id,
        )
        spec_dir = self.ctx.spec_dir
        record = self.call(read_book_record, spec_dir)
        judged = not record.findings
        return {
            "story_path": self.ctx.story_path,
            "spec_dir": spec_dir,
            "story_slug": self.ctx.story_slug,
            "story_id": self.ctx.story_id,
            "epic": self.epic,
            "qa_dir": self.ctx.qa_dir,
            "qa_scratch_dir": QA_SCRATCH_DIRNAME,
            "docs_root": str(find_docs_root(self.repo_dir)),
            "target_env": self.target_env,
            "runtime_python": sys.executable,
            "verification_setup": impl.verification_setup,
            "fixtures": [f.model_dump() for f in impl.fixtures],
            "shared_packages": list(dict.fromkeys([*impl.shared_packages, *reach.shared])),
            "qa_run_plan": [r.model_dump() for r in impl.qa_run_plan],
            "plan_services": self.call(plan_summary, spec_dir).text,
            "qa_only_scenarios": qa_only_arg(spec_dir),
            "qa_tools": self.call(qa_tools_catalog).tools,
            "standing_plan": self._standing_plan(),
            "hand_written_plan": self._hand_written_plan(),
            "compiled_plan_file": QA_COMPILED_PLAN_FILE,
            "book_services": [s.service for s in record.services] if judged else [],
            "book_unreached": list(record.unreached) if judged else [],
        }

    def _standing_plan(self) -> bool:
        """Does a `qa_plan.py` already stand that lints and validates against the packet?"""
        spec_dir = self.ctx.spec_dir
        if not spec_dir or not (Path(spec_dir) / QA_PLAN_FILE).is_file():
            return False
        if self.call(lint_qa_plan, spec_dir).status != "passed":
            return False
        return self.call(validate_qa_plan, spec_dir).status == "passed"

    def _hand_written_plan(self) -> bool:
        """Does the standing `qa_plan.py` lack the banner `compile-plan` writes, so its `covers=` are its author's and the book compiled beside it?"""
        spec_dir = self.ctx.spec_dir
        plan = Path(spec_dir) / QA_PLAN_FILE if spec_dir else None
        if plan is None or not plan.is_file():
            return False
        return not compiled_from_the_book(plan.read_text(encoding="utf-8"))

    def work(
        self,
        report: str = "",
        operator_context: str = "",
        failed_scenarios: list[dict[str, Any]] | None = None,
        laps: int = 0,
        blocks: int = 0,
    ) -> Continue | Await:
        """Run the owner turn: it selects, runs, debugs and records the story's QA."""
        self.logger.info("owning QA for %s", self.ctx.story_slug, extra={"activity": True})
        turn = roles.turn(self, "qa-story", returns=QaOwnerResult)
        with scoped_envs(self.output(stack_target).env):
            result: QaOwnerResult = self.agent(
                turn.prompt,
                returns=turn.returns,
                **self._owner_options(),
                args=turn.args
                | self._owner_args()
                | {
                    "report": report,
                    "operator_context": operator_context,
                    "failed_scenarios": failed_scenarios or [],
                },
            )
        self.call(stamp_specs, self.ctx.story_id)
        self.call(sync_story_fixtures, self.ctx.story_id)
        if result.status == "blocked":
            return self._block(result, result.notes, "the QA turn", blocks)
        return Continue(
            result,
            self.check,
            findings=[f.model_dump() for f in result.findings],
            laps=laps,
            blocks=blocks,
        )

    def recheck(self) -> Continue | Await | Done:
        """Rerun the standing plan, or the scenarios of `scope`, with no owner turn unless the stack or plan broke."""
        preflight = self._preflight()
        if self._all_judged_by_books():
            return self._finish_judged()
        failures = preflight or self._plan_failures()
        if failures:
            return self._lap(None, failures, 0, 0)
        self.logger.info("rerunning the QA plan", extra={"activity": True})
        target = self.output(stack_target)
        run = self.call(
            run_qa_plan,
            self.ctx.spec_dir,
            near=target.near,
            lease=target.lease,
            only=list(self.scope) or None,
        )
        self._file_backlog()
        self.call(stamp_specs, self.ctx.story_id)
        if run.status == "failed":
            return self._red(run, [], 0, 0, owner_classifies=False)
        if run.status != "passed":
            return self._lap(run, [unfinished_run(run)], 0, 0)
        failures = ([] if self.scope else self._evidence_failures(run)) or self._standing_failures()
        if failures:
            notes = "\n\n".join(failures)
            return self._finish("refix", run, [fallback_finding(self.ctx.qa_dir, notes)])
        self.logger.info("QA passed for %s", self.ctx.story_slug)
        return self._finish("passed", run)

    def check(
        self,
        findings: list[dict[str, Any]] | None = None,
        laps: int = 0,
        blocks: int = 0,
    ) -> Continue | Await | Done:
        """Rerun the plan the owner left, gate what it claims, and send what failed back."""
        found = [QaFinding.model_validate(f) for f in findings or []]
        failures = self._preflight() or self._plan_failures()
        if failures:
            return self._lap(None, failures, laps, blocks)
        self.logger.info("running the QA plan", extra={"activity": True})
        target = self.output(stack_target)
        run = self.call(
            run_qa_plan, self.ctx.spec_dir, near=target.near, lease=target.lease
        )
        self._file_backlog()
        self.call(stamp_specs, self.ctx.story_id)
        if run.status == "failed":
            classify = not self.stop_at_first_verdict
            return self._red(run, found, laps, blocks, owner_classifies=classify)
        if run.status != "passed":
            failures = [unfinished_run(run)]
        elif found:
            failures = [unproved_findings(found)]
        else:
            failures = self._pass_failures(run)
        if not failures:
            self.logger.info("QA passed for %s", self.ctx.story_slug)
            return self._finish("passed", run)
        if self.stop_at_first_verdict and run.status == "passed" and not found:
            notes = "\n\n".join(failures)
            return self._finish("refix", run, [fallback_finding(self.ctx.qa_dir, notes)])
        return self._lap(run, failures, laps, blocks)

    def _plan_failures(self) -> list[str]:
        """The plan's lint and its validation against the packet."""
        lint = self.call(lint_qa_plan, self.ctx.spec_dir)
        if lint.status != "passed":
            return [gate_text("qa_plan.py lint", lint.notes)]
        validation = self.call(validate_qa_plan, self.ctx.spec_dir)
        if validation.status != "passed":
            return [gate_text("qa_plan.py validation", validation.notes)]
        return []

    def _pass_failures(self, run: QaPlanRun) -> list[str]:
        """The gates a passed run must also clear before the story is believed."""
        return self._evidence_failures(run) or self._standing_failures()

    def _evidence_failures(self, run: QaPlanRun) -> list[str]:
        """The evidence gate, which reads every scenario's recording."""
        evidence = self.call(verify_qa_evidence, self.ctx.spec_dir, run.status, run.notes)
        if evidence.status != "passed":
            return [gate_text("the QA evidence", evidence.notes)]
        return []

    def _standing_failures(self) -> list[str]:
        """The gates a passed run clears whether it ran the whole plan or part of it."""
        note = self.call(check_feedback, str(self.run_dir))
        if note.present:
            return [gate_text("operator feedback", note.content)]
        suites = self.call(detect_regression_suites, self.ctx.spec_dir)
        if suites.suites:
            regression = self.call(
                run_regression_suite,
                self.ctx.spec_dir,
                self.ctx.qa_dir,
                [s.model_dump() for s in suites.suites],
            )
            if regression.status not in {"passed", "skipped"}:
                return [regression_text(regression)]
        self.call(flush_root_screenshots, self.ctx.spec_dir)
        sentinels = self.call(check_sentinel_ids, self.ctx.story_slug)
        if sentinels.status != "passed":
            return [gate_text("sentinel ids", sentinels.notes)]
        return []

    def _red(
        self,
        run: QaPlanRun,
        found: list[QaFinding],
        laps: int,
        blocks: int,
        *,
        owner_classifies: bool,
    ) -> Continue | Await | Done:
        """Send each failed scenario to the owner of the side ostler gives it."""
        sides = run_sides(run)
        if sides.environment:
            self.logger.info("QA stopped on its environment in %s", self.ctx.story_slug)
            notes = environment_failure(run, sides.environment)
            return self._ask(notes, "the QA environment", blocks)
        product = product_findings(sides.product)
        if found or product:
            return self._failed(run, [*found, *product])
        if not sides.book and not owner_classifies:
            return self._failed(run, [])
        failures = [book_failure(sides.book)] if sides.book else []
        unattributed = [s.id for s in sides.unattributed]
        if unattributed or not sides.book:
            failures.append(unclassified_failure(run, unattributed))
        ids = sorted([s.id for s in sides.book] + unattributed)
        failed = failed_scenarios_arg(self.ctx.spec_dir, ids)
        return self._lap(run, failures, laps, blocks, failed_scenarios=failed)

    def _failed(self, run: QaPlanRun, found: list[QaFinding]) -> Done:
        """A failed run with its findings: the dev owner's to fix, or the tracker's in dev."""
        if self.target_env == "dev":
            self.logger.info("QA failed for %s in dev, reported", self.ctx.story_slug)
            return self._finish("passed", run, found)
        self.logger.info("QA found product defects in %s", self.ctx.story_slug)
        return self._finish("refix", run, refix_findings(found, self.ctx.qa_dir, run.notes))

    def _finish(
        self, status: QaFlowStatus, run: QaPlanRun, findings: list[QaFinding] | None = None
    ) -> Done:
        before = self.output(snapshot_code_state).status
        changed = self.call(code_changed, before=before)
        if status == "passed":
            self.call(file_deferred_obligations, self.ctx.spec_dir)
        self._retire(status)
        return Done(
            QaFlowResult(
                status=status,
                qa=QaResult(status=run.status, notes=run.notes),
                findings=findings or [],
                docs_recheck_required=changed.changed,
            )
        )


__all__ = ["Qa"]
