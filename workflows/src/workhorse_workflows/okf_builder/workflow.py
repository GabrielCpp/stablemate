"""The okf-builder workflow: a service's code becomes an exhaustive OKF book.

Ported from `base-library/workflows/okf-builder/workflow.yaml` — 29 nodes (plus the
walk's 19, in `walkthrough_web/flow.py`) reduced to 12 states. Entry-point-first: seed
the surfaces, then drain a typed worklist where each item's investigation spawns the
deeper items it reveals (surface → elements → handler layer → callee layers → concepts
and formats), descending the code layer by layer. When the drain is dry, a deterministic
checkpoint (`ostler fmt` + `doctor`) and a computed coverage join queue whatever was
missed and loop, until the book covers the inventory. Then it walks the running app.

    workhorse-okf-builder run --params '{"service":"acme","source_path":"acme"}'

The reduction is the same four collapses `author` established, and this port is the one
that confirms them on a workflow that shares none of author's shape:

* every `decide_*` / `guard_*` `branch` node reads a value the node above it had just
  produced, so each is an `if` at the bottom of its producer. Nine of them go this way,
  including the two numeric guards (`guard_fixup_progress`, `guard_rounds`), which are
  threshold comparisons on counters and therefore two lines each;
* the counters — `round`, `rescan_round`, `stall_rounds` — and the `fixup_signature` that
  goes with them are **state parameters**, threaded along the drain rather than living in
  `vars:`. That is the mechanical difference that made the YAML's worst bug possible:
  `round` and `rescan_round` were two loops sharing one namespace, and a build that took
  40 fixup rounds to get doctor green arrived at `guard_rounds` with `round=41` and failed
  its *first* coverage re-scan on a cap about a check that had not run once. Parameters
  cannot be confused for each other — a state either takes `rescan` or it does not;
* the four `type: fail` terminals (`cannot_build`, `rounds_exhausted`, `budget_exhausted`,
  `doctor_stuck`) are `raise WorkflowFailed(...)` **at the site that decides**, with the
  reason spelled out. The YAML could only name a node;
* the `type: flow` node is `self.handoff(...)`.

Three divergences worth naming, beyond the mechanical ones the node modules record:

**`refuel: done_count` has no counterpart.** The YAML refuelled the gas tank on the
worklist's `done` count so a drain that stopped completing items would run the tank dry.
pyflow has no gas tank; the transition budget bounds the machine instead. A drain that
stops completing items still terminates, but it terminates on a *transition* count rather
than on the observation that nothing is progressing — a coarser signal, and the one thing
this port loses. It is a finding, not a silent absorption: see the ledger.

**`recheck` reads its coverage bundle with `self.output(...)`.** The YAML passed eleven
template arguments to that turn, six of them just copied through two states from
`inventory_source` and `compute_coverage`. `self.output(node)` re-reads the node's
recorded `output.json`, so those six survive a resume exactly as a checkpointed parameter
would — the checkpoint here is coarse and re-enters the state from the top, and the run
dir is on disk either way. Parameters carry what a state *branches* on; this is what it
merely quotes.

**`select_item` is called with `done_baseline` here and without it in the walk.** That is
the YAML's own asymmetry, preserved: the build's `max_items` bounds *this run*, the walk's
bounds the worklist's lifetime. See `walkthrough_web/flow.py`.
"""
from __future__ import annotations

from workhorse.cli import console_script
from workhorse.pyflow import Continue, Done, NodeNotRunError, Registry, Workflow, WorkflowFailed
from workhorse_workflows.okf_builder.nodes import (
    auto_waive,
    compute_coverage,
    inventory_source,
    prepare,
)
from workhorse_workflows.okf_builder.shared import paths
from workhorse_workflows.okf_builder.shared.blueprint import blueprint
from workhorse_workflows.okf_builder.shared.checkpoint import checkpoint_book
from workhorse_workflows.okf_builder.shared.schemas import Discovery, Investigation, Prepared, Recheck
from workhorse_workflows.okf_builder.shared.worklist import record, select_item
from workhorse_workflows.okf_builder.walkthrough_web import WalkthroughWeb

#: Coverage re-scans before the build gives up. Bounds the *dry-drain* loop only — the
#: fixup loop is bounded by `MAX_STALL_ROUNDS` below, and by nothing else, because a big
#: book's fixup rounds are productive and capping them would cap the work.
MAX_RESCAN_ROUNDS = 6

#: Consecutive rounds an unchanged doctor finding set is tolerated before the run stops
#: re-drilling it and hands it to `auto_waive`. A repair that has not landed in three
#: identical rounds is a repair that cannot land in the book.
MAX_STALL_ROUNDS = 3


class OkfBuilder(Workflow):
    """Build (or repair) one service's OKF book from its source, exhaustively.

    The stop condition is convergence, not a budget: the run ends when the computed
    coverage join is complete and `ostler doctor` is green. `max_items` is a safety valve
    for a quota-limited practice run, and reaching it is a **failure** — a partial book
    must not read as a finished one.
    """

    #: Which `<features-root>/<service>` book to build, the root being ostler's answer;
    #: `""` = the whole tree.
    service: str = ""
    #: Source subtree to inventory; defaults to `service`.
    source_path: str = ""
    #: Comma-separated paths under `source_path` that are not part of this book.
    source_excludes: str = ""
    #: Skip discovery and re-enter at the checkpoint — repair an already-populated book.
    #: A `"yes"`/`"no"` var in the YAML, a bool here.
    recheck_only: bool = False
    #: The docs repo root; `""` walks up from `repo_dir`, the run's own checkout.
    docs_path: str = ""
    #: Optional per-run investigation ceiling. 0 = run to convergence.
    max_items: int = 0

    def setup(self) -> Prepared:
        """Resolve every path and adopt (or reset) the worklist.

        `prepare` is `setup` rather than a state for the reason `research`'s clone is: it
        is the run's *setting*, every state reads it, and no state decides it. Its failure
        mode is carried as data — `ostler_ok=False` plus a `prepare_error` — so the
        decision to fail stays in `start`, where a reader looking for the exits finds it.
        """
        return self.call(
            prepare, self.docs_path, self.service, self.source_path, self.source_excludes
        )

    def labels(self) -> dict[str, str]:
        """The dashboard's dimensions: which item, and how far through the drain.

        The YAML's three `labels:` templates, verbatim in effect — `work_id` and
        `progress` off `select_item`'s recorded output, `service` off the run's own input.
        Before the first pick there is nothing to read, and the guard drops those two
        rather than stamping them blank.
        """
        labels = {"service": self.service}
        try:
            pick = self.output(select_item)
        except NodeNotRunError:
            return labels
        return {**labels, "work_id": pick.item_target, "progress": pick.progress}

    # --- seeding ------------------------------------------------------------

    def start(self) -> Continue:
        """`check_ostler` + `decide_start`: can this run measure anything, and from where.

        No ostler, no graph, or an unusable source root and the run cannot measure what it
        would go on to claim. That is a failure and not a quiet exit — a build that
        documented nothing because its instrument was missing must not be
        indistinguishable from a build that is done.
        """
        if not self.ctx.ostler_ok:
            raise WorkflowFailed(
                self.ctx.prepare_error
                or "ostler could not load a graph at the docs root, so nothing this run "
                "claimed about coverage could be checked"
            )
        if self.recheck_only:
            self.logger.info("recheck-only: re-entering at the checkpoint, skipping discovery")
            return Continue(None, self.checkpoint)
        return Continue(None, self.enumerate_surfaces)

    def enumerate_surfaces(self) -> Continue:
        """Identify every entry-point surface from the code.

        Their internals are not this turn's job: the drain discovers them, one layer at a
        time, which is what keeps this prompt's scope constant regardless of book size.
        """
        self.logger.info("enumerating %s's surfaces", self.service or "the repo")
        result = self.agent(
            "prompts/enumerate-surfaces.md",
            returns=Discovery,
            power="medium",
            cwd=self.ctx.repo_root,
            add_dirs=[self.ctx.repo_root],
            args={
                "service": self.service,
                "features_root": self.ctx.features_root,
                "repo_root": self.ctx.repo_root,
                "source_root": self.ctx.source_root,
                "source_excludes": self.ctx.source_excludes,
            },
        )
        return Continue(result, self.seed_surfaces, discovered=result.discovered)

    def seed_surfaces(self, discovered: list[dict]) -> Continue:
        """`seed_surfaces`: open the surfaces, close nothing."""
        return Continue(
            self.call(record, self.ctx.worklist_path, None, discovered), self.select
        )

    # --- the drain ----------------------------------------------------------

    def select(
        self, rnd: int = 0, rescan: int = 0, stall: int = 0, signature: str = ""
    ) -> Continue:
        """`select_item` + `guard_budget` + `decide_item`: take one item, or converge.

        The four counters ride along untouched. They belong to the *convergence* loop, not
        to this one, but a drain re-entered from a fixup round has to hand them back to
        `checkpoint` when it goes dry — which is exactly what the YAML's run-global `vars`
        did implicitly and what these four parameters do visibly.
        """
        pick = self.call(
            select_item, self.ctx.worklist_path, self.max_items, self.ctx.done_baseline
        )
        if pick.over_budget:
            # The valve, not the stop condition. Canonicalize what was built so the
            # partial book is at least well-formed, then fail: pending items survive for
            # a resume, which gets its own allowance off a fresh `done_baseline`.
            self.call(checkpoint_book, self.ctx.repo_root, self.ctx.features_root, rnd)
            raise WorkflowFailed(
                f"stopped at the {self.max_items}-item ceiling with {pick.pending_count} "
                f"item(s) still pending — the book is partial, not converged. Re-run to "
                f"resume with a fresh allowance."
            )
        if not pick.has_item:
            return Continue(
                pick,
                self.checkpoint,
                rnd=rnd,
                rescan=rescan,
                stall=stall,
                signature=signature,
            )
        return Continue(
            pick,
            self.investigate,
            current_item=pick.current_item,
            item_kind=pick.item_kind,
            item_code=pick.item_code,
            item_target=pick.item_target,
            item_context=pick.item_context,
            progress=pick.progress,
            rnd=rnd,
            rescan=rescan,
            stall=stall,
            signature=signature,
        )

    def investigate(
        self,
        current_item: dict,
        item_kind: str,
        item_target: str,
        item_context: str,
        item_code: str = "",
        progress: str = "",
        rnd: int = 0,
        rescan: int = 0,
        stall: int = 0,
        signature: str = "",
    ) -> Continue:
        """The heart: document ONE item to the spec-complete bar.

        The turn returns the deeper items it revealed — elements, code layers, concepts,
        formats, journeys, fixups — and nothing else here reads them; `record_item` does.
        Keeping the worklist write in its own state is what makes a crash mid-turn
        re-investigate rather than close an item nothing documented.
        """
        where = f"documenting {item_kind} {item_target}"
        self.logger.info(
            "%s%s", where, f" · {progress}" if progress else "", extra={"activity": True}
        )
        result = self.agent(
            "prompts/investigate.md",
            returns=Investigation,
            power="medium",
            cwd=self.ctx.repo_root,
            add_dirs=[self.ctx.repo_root],
            args={
                "item_kind": item_kind,
                "item_code": item_code,
                "item_target": item_target,
                "item_context": item_context,
                "service": self.service,
                "features_root": self.ctx.features_root,
                "repo_root": self.ctx.repo_root,
                "source_root": self.ctx.source_root,
                "source_excludes": self.ctx.source_excludes,
            },
        )
        return Continue(
            result,
            self.record_item,
            current_item=current_item,
            discovered=result.discovered,
            rnd=rnd,
            rescan=rescan,
            stall=stall,
            signature=signature,
        )

    def record_item(
        self,
        current_item: dict,
        discovered: list[dict],
        rnd: int = 0,
        rescan: int = 0,
        stall: int = 0,
        signature: str = "",
    ) -> Continue:
        """`record`: close the item the turn documented, open what it revealed."""
        return Continue(
            self.call(record, self.ctx.worklist_path, current_item, discovered),
            self.select,
            rnd=rnd,
            rescan=rescan,
            stall=stall,
            signature=signature,
        )

    # --- convergence: the mechanical gate ------------------------------------

    def checkpoint(
        self, rnd: int = 0, rescan: int = 0, stall: int = 0, signature: str = ""
    ) -> Continue:
        """`checkpoint` + `decide_checkpoint` + `guard_fixup_progress` + `seed_fixup` +
        `guard_rounds`: canonicalize, read doctor, and decide what the dirt means.

        The two guards this state absorbs bound *different* loops and are deliberately
        kept apart:

        * dirty doctor whose finding set has not changed in `MAX_STALL_ROUNDS` rounds → a
          repair that cannot land in the book, so hand it to `waive`;
        * clean doctor after `MAX_RESCAN_ROUNDS` coverage re-scans → the coverage check is
          not converging, so stop. Reaching the cap is **not** convergence and says so.
        """
        result = self.call(
            checkpoint_book,
            self.ctx.repo_root,
            self.ctx.features_root,
            rnd,
            signature,
            stall,
        )
        if not result.checkpoint_clean:
            if result.stall_rounds >= MAX_STALL_ROUNDS:
                return Continue(
                    result,
                    self.waive,
                    rnd=result.round,
                    rescan=rescan,
                    stall=result.stall_rounds,
                    signature=result.fixup_signature,
                )
            return Continue(
                self.call(record, self.ctx.worklist_path, None, result.fixup_items),
                self.select,
                rnd=result.round,
                rescan=rescan,
                stall=result.stall_rounds,
                signature=result.fixup_signature,
            )
        if rescan >= MAX_RESCAN_ROUNDS:
            raise WorkflowFailed(
                f"the coverage re-scan did not converge in {MAX_RESCAN_ROUNDS} rounds — "
                f"the book is still short of its source inventory and this run gave up "
                f"rather than loop. This is not a finished book."
            )
        return Continue(result, self.rescan_coverage, rnd=result.round, rescan=rescan)

    def waive(
        self, rnd: int = 0, rescan: int = 0, stall: int = 0, signature: str = ""
    ) -> Continue:
        """`auto_waive` + `decide_auto_waive`: accept what a doc edit cannot fix, or stop.

        Each code-fix-only a11y defect gets a warn-level doctor waiver plus a backlog IOU
        naming the real fix, the un-waive step and the re-run that confirms it, so the next
        checkpoint sees a warning and the book converges. A finding that is *not*
        auto-waivable ends the run honestly rather than being papered over.

        `stall` and `signature` go back to `checkpoint` unchanged, matching the YAML, where
        the vars simply persisted across the round trip: if the waivers did not in fact
        change what doctor reports, the very next round counts as another stalled one and
        the second pass through here lands on the same unwaivable finding.
        """
        result = self.call(
            auto_waive, self.ctx.repo_root, self.ctx.features_root, self.service
        )
        if result.has_unwaivable:
            raise WorkflowFailed(
                "the fixup loop stalled on a finding that is neither doc-repairable nor "
                f"auto-waivable, so doctor cannot be made clean: {result.note}"
            )
        return Continue(
            result,
            self.checkpoint,
            rnd=rnd,
            rescan=rescan,
            stall=stall,
            signature=signature,
        )

    # --- convergence: the exhaustiveness re-scan ------------------------------

    def rescan_coverage(self, rnd: int = 0, rescan: int = 0) -> Continue:
        """`inventory_source` + `compute_coverage` + `decide_coverage`.

        Two nodes in one state because the second consumes the first's only output and
        nothing decides between them — the inventory is not a checkpoint anyone would want
        to resume *into*, it is a file re-derived from source in seconds.

        The verdict is arithmetic, not an agent's self-report: the join of the book's
        `code:` citations against the inventory. The agent's role begins below, on the rows
        this says are missing.
        """
        inventory = self.call(
            inventory_source,
            self.ctx.source_root,
            str(paths.source_inventory_path(self.ctx.worklist_path)),
            self.ctx.source_excludes,
            self.ctx.repo_root,
        )
        coverage = self.call(
            compute_coverage,
            self.ctx.repo_root,
            self.ctx.features_root,
            self.service,
            inventory.source_inventory_path,
            str(paths.waivers_path(self.ctx.features_root)),
            rescan,
        )
        # One gap left to test here. The other — every cited node declaring what observing
        # it looks like — used to be re-read at this point because the checkpoint drained
        # errors only and `undeclared-obligation` is a warn. The checkpoint is severity-
        # blind now, and this state is reachable only through a *clean* one, so asking again
        # would be a second, weaker reader of a question already answered upstream.
        if coverage.coverage_complete:
            return Continue(coverage, self.walkthrough)
        return Continue(coverage, self.recheck, rnd=rnd, rescan=coverage.rescan_round)

    def recheck(self, rnd: int = 0, rescan: int = 0) -> Continue:
        """Adjudicate the computed missing list — the only coverage judgement left to an agent.

        It no longer votes on completeness. It receives the rows the join reports missing
        and rules on the ambiguous ones — a helper folded into a documented contract, a
        deliberate non-unit — recording each verdict with a reason in the committed waivers
        file, and queueing the rest as real work.

        The eleven template arguments the YAML built are six reads off the two nodes
        `rescan_coverage` just ran plus five values already on `self`.
        """
        inventory = self.output(inventory_source)
        coverage = self.output(compute_coverage)
        self.logger.info(
            "adjudicating %d uncovered unit(s), re-scan %d",
            coverage.missing_count,
            rescan,
            extra={"activity": True},
        )
        result = self.agent(
            "prompts/recheck-coverage.md",
            returns=Recheck,
            power="medium",
            cwd=self.ctx.repo_root,
            add_dirs=[self.ctx.repo_root],
            args={
                "service": self.service,
                "features_root": self.ctx.features_root,
                "repo_root": self.ctx.repo_root,
                "source_root": self.ctx.source_root,
                "source_excludes": self.ctx.source_excludes,
                "source_inventory_path": inventory.source_inventory_path,
                "inventory_errors": inventory.inventory_errors,
                "missing_path": coverage.missing_path,
                "missing_count": coverage.missing_count,
                "coverage_summary": coverage.coverage_summary,
                "coverage_error": coverage.coverage_error,
                "waivers_path": str(paths.waivers_path(self.ctx.features_root)),
            },
        )
        return Continue(
            result, self.seed_recheck, discovered=result.discovered, rnd=rnd, rescan=rescan
        )

    def seed_recheck(
        self, discovered: list[dict], rnd: int = 0, rescan: int = 0
    ) -> Continue:
        """`seed_recheck`: queue what the adjudication ruled to be real work.

        Back to the drain with `stall`/`signature` at their defaults, which is where the
        clean checkpoint that got us here had already put them: doctor was green, so the
        finding set was empty and `checkpoint.py` zeroed the stall itself.
        """
        return Continue(
            self.call(record, self.ctx.worklist_path, None, discovered),
            self.select,
            rnd=rnd,
            rescan=rescan,
        )

    # --- the live-app walk ---------------------------------------------------

    def walkthrough(self) -> Done:
        """Hand the complete book to the walk, and end on what it found.

        A no-op for a service with no web surface — the sub-flow's own `detect_webapp`
        decides that, and it decides it by reading the book rather than by being told,
        which is what lets the same flow be invoked standalone.
        """
        return Done(
            self.handoff(
                WalkthroughWeb,
                service=self.service,
                docs_path=self.docs_path,
                source_path=self.source_path,
                max_items=self.max_items,
            )
        )


workflow = (
    Registry("okf-builder")
    .add_blueprints(blueprint)
    .add_flows(**{"walkthrough-web": WalkthroughWeb})
    .stub_agents(
        {
            # Keyed by prompt STEM. Each is the reply that makes a dry run *progress*
            # past its gate; see `shared/stubs.py` for why the blank default does not.
            "enumerate-surfaces": {"discovered": []},
            "investigate": {"doc_status": "documented"},
            "recheck-coverage": {"needs_journeys": False},
            "walkthrough-web": {"walk_status": "confirmed"},
        }
    )
)
main = console_script(workflow.entry_point(OkfBuilder))


__all__ = ["MAX_RESCAN_ROUNDS", "MAX_STALL_ROUNDS", "OkfBuilder", "main", "workflow"]
