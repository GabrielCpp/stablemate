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
* the YAML's four `type: fail` terminals are decided **at the site that decides**, with
  the reason spelled out — the YAML could only name a node. Two of them are still
  `raise WorkflowFailed(...)`: a run that cannot measure (`cannot_build`) and a finding
  that is neither repairable nor waivable (`doctor_stuck`). The other two —
  `budget_exhausted` and `rounds_exhausted` — are budget stops, not defects, and a
  workflow never gives up on a budget: they are operator gates (`Await`) now, resumable
  with a fresh allowance;
* the `type: flow` node is `self.handoff(...)`.

Three divergences worth naming, beyond the mechanical ones the node modules record:

**`refuel: done_count` is `REFUEL_ON`.** The YAML refuelled the gas tank on the worklist's
`done` count so a drain that stopped completing items would run the tank dry. pyflow has
no gas tank, and for a while the transition budget stood in for one — which terminated a
stalled drain, but on a *transition* count rather than on the observation that nothing is
progressing. That is a coarser signal and it has a failure mode the YAML did not: a 4,378
item backlog exhausts 1,000 transitions while perfectly healthy, and dies. `REFUEL_ON`
below restores the original reading — the budget bounds transitions *since the last
completed item*, so the backlog's size stops being a thing an operator has to have
predicted, and a ping-pong still dies on the same 1,000.

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

from pathlib import Path
from typing import ClassVar

from workhorse.pyflow import Await, Continue, Done, NodeNotRunError, Workflow, WorkflowFailed
from workhorse_workflows.okf_builder.main.nodes import (
    advance_watermark,
    auto_waive,
    compute_coverage,
    inventory_source,
    prepare,
)
from workhorse_workflows.okf_builder.shared import paths
from workhorse_workflows.okf_builder.shared.checkpoint import checkpoint_book
from workhorse_workflows.okf_builder.shared.schemas import (
    Discovery,
    Investigation,
    Prepared,
    Recheck,
    Recorded,
    SourceRequest,
)
from workhorse_workflows.okf_builder.shared.vocabulary import bullet_grammar, check_vocabulary
from workhorse_workflows.okf_builder.shared.worklist import (
    MAX_TARGET_ATTEMPTS,
    record,
    select_item,
)
from workhorse_workflows.okf_builder.walkthrough_web import WalkthroughWeb

#: Coverage re-scans before the build gives up. Bounds the *dry-drain* loop only. The
#: fixup loop is not capped by a round count — a big book's fixup rounds are productive
#: and capping them would cap the work. It is bounded per *target* instead, by
#: `MAX_TARGET_ATTEMPTS` in `shared/worklist.py`.
MAX_RESCAN_ROUNDS = 6

#: Consecutive rounds an unchanged doctor finding set is tolerated before the run stops
#: re-drilling it and hands it to `auto_waive`. A repair that has not landed in three
#: identical rounds is a repair that cannot land in the book.
#:
#: This is the *whole-book* signal, and it was the only one there used to be — which is
#: why the loop was unbounded in practice. It moves whenever any finding anywhere moves,
#: so on a four-thousand-item book it essentially never repeats. What actually stops a
#: stubborn repair is the per-target counter; this stays as the coarse backstop it was.
MAX_STALL_ROUNDS = 3


class OkfBuilder(Workflow):
    """Build (or repair) one service's OKF book from its source, exhaustively.

    The stop condition is convergence, not a budget: the run ends when the computed
    coverage join is complete and `ostler doctor` is green. `max_items` is a safety valve
    for a quota-limited practice run, and reaching it **blocks** the run on an operator
    gate rather than ending it — a partial book must not read as a finished one, and a
    budget stop is not a defect, so the run waits for a fresh allowance instead of dying.
    """

    #: `select` reports `"3386/4378"` and the drain threads it down to `investigate`, so
    #: it moves exactly when an item is closed or a new one is discovered — the YAML's
    #: `refuel: done_count`, restored. A backlog of four thousand items no longer needs
    #: an operator to have guessed four thousand items' worth of transitions in advance;
    #: a drain that stops closing items still dies on the same 1,000.
    REFUEL_ON: ClassVar[frozenset[str]] = frozenset({"progress"})

    #: Which `<features-root>/<service>` book to build, the root being ostler's answer;
    #: `""` = the whole tree.
    service: str = ""
    #: Source subtree to inventory; defaults to `service`.
    source_path: str = ""
    #: Comma-separated paths under `source_path` that are not part of this book.
    source_excludes: str = ""
    #: The docs repo root; `""` walks up from `repo_dir`, the run's own checkout.
    docs_path: str = ""
    #: Optional per-run investigation ceiling. 0 = run to convergence.
    max_items: int = 0
    #: Narrow the run to what changed since this revision — every path differing from its
    #: merge base with HEAD, working tree and untracked included. `""` reconciles the whole
    #: book. A narrowing that cannot be computed blocks the run rather than silently
    #: widening to a full scan or narrowing to nothing.
    since: str = ""

    #: Retired and unread, kept declared for one release. They selected between two prepare
    #: functions and three ways of computing what was stale; one reconcile against the
    #: book's own watermark answers all of them, so `since` is the only narrowing left and
    #: `recheck_only` falls out of the book already existing. Deleting a field kills every
    #: in-flight run on reload with a bare pydantic `extra_forbidden`, so a run that passes
    #: one gets a warning out of `prepare`, not a crash.
    recheck_only: bool = False
    diff_base: str = ""
    story: str = ""
    workspace_file: str = ""
    sources: tuple[SourceRequest, ...] = ()

    def setup(self) -> Prepared:
        """Resolve every path and adopt (or reset) the worklist.

        `prepare` is `setup` rather than a state for the reason `research`'s clone is: it
        is the run's *setting*, every state reads it, and no state decides it. Its failure
        mode is carried as data — `ostler_ok=False` plus a `prepare_error` — so the
        decision to fail stays in `start`, where a reader looking for the exits finds it.
        """
        return self.call(
            prepare,
            self.docs_path,
            self.service,
            self.source_path,
            self.source_excludes,
            since=self.since,
            recheck_only=self.recheck_only,
            diff_base=self.diff_base,
            story=self.story,
            workspace_file=self.workspace_file,
            sources=self.sources,
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

        Then the run's one entry decision, and it is read off the book rather than passed
        in. A book that already holds markdown is **reconciled** to HEAD: the checkpoint
        reads doctor, the coverage join reads the watermark, and between them they name
        every unit the book owes work on — which is exactly what `recheck_only` used to ask
        for by hand, and forgetting it re-enumerated a finished book's surfaces every run.
        An empty book has nothing to reconcile against, so it is filled top-down from the
        code's entry surfaces.
        """
        if not self.ctx.ostler_ok:
            raise WorkflowFailed(
                self.ctx.prepare_error
                or "ostler could not load a graph at the docs root, so nothing this run "
                "claimed about coverage could be checked",
                failure_class="okf-builder-ostler-not-ok",
                artifacts={"features_root": str(self.ctx.features_root)},
            )
        if self.ctx.book_exists:
            self.logger.info("the book exists: reconciling it to HEAD from the checkpoint")
            return Continue(None, self.checkpoint)
        self.logger.info("no book yet: filling it top-down from the code's entry surfaces")
        return Continue(None, self.enumerate_surfaces)

    def enumerate_surfaces(self) -> Continue:
        """Identify every entry-point surface from the code.

        Their internals are not this turn's job: the drain discovers them, one layer at a
        time, which is what keeps this prompt's scope constant regardless of book size.
        """
        self.logger.info("enumerating %s's surfaces", self.service or "the repo")
        result = self.agent(
            "main/prompts/enumerate-surfaces.md",
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
                "diff_scope_path": self.ctx.diff_scope_path,
                "diff_scope_count": self.ctx.diff_scope_count,
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
        self,
        rnd: int = 0,
        rescan: int = 0,
        stall: int = 0,
        signature: str = "",
        refuels: int = 0,
    ) -> Continue | Await:
        """`select_item` + `guard_budget` + `decide_item`: take one item, or converge.

        The counters ride along untouched. They belong to the *convergence* loop, not
        to this one, but a drain re-entered from a fixup round has to hand them back to
        `checkpoint` when it goes dry — which is exactly what the YAML's run-global `vars`
        did implicitly and what these parameters do visibly. `refuels` is the one that
        belongs to *this* guard: each operator pass through `refuel` grants one more
        `max_items` allowance on top of the baseline `prepare` froze at setup.
        """
        pick = self.call(
            select_item,
            self.ctx.worklist_path,
            self.max_items * (refuels + 1) if self.max_items else 0,
            self.ctx.done_baseline,
        )
        if pick.over_budget:
            # The valve, not the stop condition — and a budget, not a defect, so the run
            # blocks instead of dying. Canonicalize what was built so the partial book is
            # at least well-formed, then hand the stop to the operator: answering the
            # gate file resumes at `refuel`, which grants another `max_items`.
            self.call(checkpoint_book, self.ctx.repo_root, self.ctx.features_root, rnd)
            return Await(
                paths.operator_context_path(
                    Path(self.ctx.repo_root), self.service, self.ctx.scope_id
                ),
                f"okf-builder stopped at its {self.max_items * (refuels + 1)}-item "
                f"ceiling with {pick.pending_count} item(s) still pending — the book "
                f"is partial, not converged. It was canonicalized (`ostler fmt`) so "
                f"what exists is well-formed. Flip this file's `STATUS:` line to "
                f"`ANSWERED` to resume the drain with a fresh allowance of "
                f"{self.max_items} item(s).",
                self.refuel,
                rnd=rnd,
                rescan=rescan,
                stall=stall,
                signature=signature,
                refuels=refuels,
            )
        if not pick.has_item:
            return Continue(
                pick,
                self.checkpoint,
                rnd=rnd,
                rescan=rescan,
                stall=stall,
                signature=signature,
                refuels=refuels,
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
            refuels=refuels,
        )

    def refuel(
        self,
        rnd: int = 0,
        rescan: int = 0,
        stall: int = 0,
        signature: str = "",
        refuels: int = 0,
    ) -> Continue:
        """Consume the operator's answer to an item-ceiling stop: one more allowance.

        Exists so the `Await` above has a cheap-prefix target that does the one thing a
        resume means here — grant another `max_items` and re-enter the drain. Re-entering
        `select` directly would re-arrive at the same guard with the same allowance and
        block again; the increment has to live on the far side of the wait.
        """
        self.logger.info(
            "operator refuel #%d: granting %d more item(s)", refuels + 1, self.max_items
        )
        return Continue(
            None,
            self.select,
            rnd=rnd,
            rescan=rescan,
            stall=stall,
            signature=signature,
            refuels=refuels + 1,
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
        refuels: int = 0,
    ) -> Continue:
        """The heart: document ONE item to the spec-complete bar, or repair one finding.

        The turn returns the deeper items it revealed — elements, code layers, concepts,
        formats, journeys — and nothing else here reads them; `record_item` does. Keeping the
        worklist write in its own state is what makes a crash mid-turn re-investigate rather
        than close an item nothing documented.

        **Two prompts, chosen by the kind.** A discovery item (`surface`, `layer`, `element`,
        …) gets `investigate.md`. A repair item from the checkpoint — `fix:<code>`, which by
        construction carries one doctor code on one node — gets `repair.md`, which dispatches
        to a fragment written for that code. That dispatch is the whole reason the checkpoint
        splits items per code: a prompt can only be written for a defect that is known before
        the turn starts.

        A repair turn also carries the **check vocabulary and its signatures**, rendered from
        `ostler.checks` rather than described. The first live backfill turns wrote
        `count(subject=…, expected=1)` and `visible(locator="PDFEngine output", …)` — a check
        that does not exist and an argument that does not — because the prompt named the
        vocabulary (`ostler checks` lists it) instead of containing it, and a repair turn asked
        for one small edit does not go looking. Each of those came straight back as a fresh
        `unparsed-check`, so the round spent money to move a finding sideways.
        """
        repair = item_kind.startswith("fix:")
        where = f"{'repairing' if repair else 'documenting'} {item_kind} {item_target}"
        self.logger.info(
            "%s%s", where, f" · {progress}" if progress else "", extra={"activity": True}
        )
        result = self.agent(
            "main/prompts/repair.md" if repair else "main/prompts/investigate.md",
            returns=Investigation,
            power="medium",
            cwd=self.ctx.repo_root,
            add_dirs=[self.ctx.repo_root],
            args={
                "item_kind": item_kind,
                "item_code": item_code,
                "item_target": item_target,
                "item_context": item_context,
                "check_vocabulary": check_vocabulary(),
                "bullet_grammar": bullet_grammar(),
                "source_inventory_path": str(
                    paths.source_inventory_path(self.ctx.worklist_path)
                ),
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
            item_kind=item_kind,
            item_context=item_context,
            # For *every* kind. A repair turn that answers `partial` or `skipped` is
            # reporting that this finding cannot be cleared from the book, and that verdict
            # used to be read at one callsite gated on the retired `change` kind — so it was
            # discarded for every `fix:` item ever produced, the item closed `done`
            # regardless, and doctor raised the same finding again next round.
            doc_status=result.doc_status,
            note=result.note,
            rnd=rnd,
            rescan=rescan,
            stall=stall,
            signature=signature,
            refuels=refuels,
        )

    def record_item(
        self,
        current_item: dict,
        discovered: list[dict],
        item_kind: str = "",
        item_context: str = "",
        doc_status: str = "",
        note: str = "",
        rnd: int = 0,
        rescan: int = 0,
        stall: int = 0,
        signature: str = "",
        refuels: int = 0,
    ) -> Continue:
        """`record`: close the item the turn documented, open what it revealed.

        The turn's own `doc_status` rides along and is stored on the row it closes, so the
        next round's re-queue of that same target has the last turn's reason to carry into
        `blocked_reason` when the attempts run out.

        A regrounding item also moves its own watermark here, before the row closes. The two
        writes belong in one state because they are one fact — this node now describes these
        bytes — and a run that recorded the close without the watermark would be handed the
        same node again by the next join, forever.
        """
        self.call(
            advance_watermark,
            self.ctx.repo_root,
            item_kind,
            item_context,
            doc_status,
        )
        return Continue(
            self.call(
                record,
                self.ctx.worklist_path,
                current_item,
                discovered,
                doc_status=doc_status,
                note=note,
            ),
            self.select,
            rnd=rnd,
            rescan=rescan,
            stall=stall,
            signature=signature,
            refuels=refuels,
        )

    # --- convergence: the mechanical gate ------------------------------------

    def checkpoint(
        self,
        rnd: int = 0,
        rescan: int = 0,
        stall: int = 0,
        signature: str = "",
        refuels: int = 0,
    ) -> Continue | Await:
        """`checkpoint` + `decide_checkpoint` + `guard_fixup_progress` + `seed_fixup` +
        `guard_rounds`: canonicalize, read doctor, and decide what the dirt means.

        The two guards this state absorbs bound *different* loops and are deliberately
        kept apart:

        * dirty doctor whose finding set has not changed in `MAX_STALL_ROUNDS` rounds → a
          repair that cannot land in the book, so hand it to `waive`;
        * clean doctor after `MAX_RESCAN_ROUNDS` coverage re-scans → the coverage check is
          not converging. Reaching the cap is **not** convergence — but it is a budget,
          not a defect, so it blocks on the operator gate; answering the gate file
          resumes the re-scan with a fresh round allowance.
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
            # Seed before deciding. A repair item's identity is stable now, so this write
            # is also where a survivor's `attempts` is incremented and where a target that
            # has spent them stops being handed back out — and the decision below reads
            # that outcome.
            recorded = self.call(record, self.ctx.worklist_path, None, result.fixup_items)
            if recorded.blocked_count and not recorded.pending_count:
                return Await(
                    paths.operator_context_path(Path(self.ctx.repo_root), self.service),
                    self._blocked_gate_question(recorded),
                    self.retry_blocked,
                    rnd=result.round,
                    rescan=rescan,
                    signature=result.fixup_signature,
                    refuels=refuels,
                )
            if result.stall_rounds >= MAX_STALL_ROUNDS:
                return Continue(
                    result,
                    self.waive,
                    rnd=result.round,
                    rescan=rescan,
                    stall=result.stall_rounds,
                    signature=result.fixup_signature,
                    refuels=refuels,
                )
            return Continue(
                recorded,
                self.select,
                rnd=result.round,
                rescan=rescan,
                stall=result.stall_rounds,
                signature=result.fixup_signature,
                refuels=refuels,
            )
        if rescan >= MAX_RESCAN_ROUNDS:
            return Await(
                paths.operator_context_path(Path(self.ctx.repo_root), self.service),
                f"okf-builder's coverage re-scan did not converge in "
                f"{MAX_RESCAN_ROUNDS} rounds — doctor is clean but the book is still "
                f"short of its source inventory, so each re-scan keeps finding "
                f"uncovered units. This is not a finished book. Look at the missing "
                f"list beside the worklist under .agents/okf-build/ to see what keeps "
                f"coming back, then flip this file's `STATUS:` line to `ANSWERED` to "
                f"resume the re-scan with a fresh {MAX_RESCAN_ROUNDS}-round allowance.",
                self.rescan_coverage,
                rnd=result.round,
                rescan=0,
                refuels=refuels,
            )
        return Continue(
            result, self.rescan_coverage, rnd=result.round, rescan=rescan, refuels=refuels
        )

    @staticmethod
    def _blocked_gate_question(recorded: Recorded) -> str:
        """Name every target that spent its attempts, so the gate is actionable.

        A gate that says only "the fixup loop is stuck" costs the operator the whole
        investigation this run already did. Each line is the doctor code, the node it sits
        on, how many turns were spent on it and what the last of those turns said.
        """
        lines = "\n".join(
            f"  - {b.get('target', '?')} ({b.get('kind', '?')}) — "
            f"{b.get('attempts', 0)} attempt(s); last turn said: "
            f"{b.get('reason') or 'nothing'}"
            for b in recorded.blocked
        )
        return (
            f"okf-builder cannot clear {recorded.blocked_count} doctor finding(s) from the "
            f"book. Each was handed to a repair turn {MAX_TARGET_ATTEMPTS} times and came "
            f"back standing, and there is no other work left on the worklist:\n\n"
            f"{lines}\n\n"
            f"These are not waived — doctor still reports them. Either repair them by "
            f"hand, or decide the finding is wrong and fix the detector. Then set this "
            f"file's `STATUS:` line to `ANSWERED` to return those targets to the drain "
            f"with a fresh {MAX_TARGET_ATTEMPTS}-attempt allowance."
        )

    def retry_blocked(
        self,
        rnd: int = 0,
        rescan: int = 0,
        signature: str = "",
        refuels: int = 0,
    ) -> Continue:
        """The operator answered: return the blocked targets to the drain.

        `stall` is not threaded through and restarts at zero deliberately. The operator's
        answer is a statement that something changed — a hand repair, a detector fix — and
        carrying the pre-gate stall count in would spend the next two rounds walking
        straight into `waive` on a finding set nobody has re-read yet.
        """
        return Continue(
            self.call(record, self.ctx.worklist_path, unblock=True),
            self.select,
            rnd=rnd,
            rescan=rescan,
            stall=0,
            signature=signature,
            refuels=refuels,
        )

    def waive(
        self,
        rnd: int = 0,
        rescan: int = 0,
        stall: int = 0,
        signature: str = "",
        refuels: int = 0,
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
                f"auto-waivable, so doctor cannot be made clean: {result.note}",
                failure_class="okf-builder-unwaivable-finding",
                artifacts={"features_root": str(self.ctx.features_root)},
            )
        return Continue(
            result,
            self.checkpoint,
            rnd=rnd,
            rescan=rescan,
            stall=stall,
            signature=signature,
            refuels=refuels,
        )

    # --- convergence: the exhaustiveness re-scan ------------------------------

    def rescan_coverage(self, rnd: int = 0, rescan: int = 0, refuels: int = 0) -> Continue:
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
            self.ctx.diff_scope_path,
        )
        coverage = self.call(
            compute_coverage,
            self.ctx.repo_root,
            self.ctx.features_root,
            self.service,
            inventory.source_inventory_path,
            str(paths.waivers_path(self.ctx.features_root)),
            rescan,
            scoped=bool(self.ctx.diff_scope_path),
        )
        # One gap left to test here. The other — every cited node declaring what observing
        # it looks like — used to be re-read at this point because the checkpoint drained
        # errors only and `undeclared-obligation` is a warn. The checkpoint is severity-
        # blind now, and this state is reachable only through a *clean* one, so asking again
        # would be a second, weaker reader of a question already answered upstream.
        if coverage.coverage_complete:
            return Continue(coverage, self.walkthrough)
        if coverage.regrounding:
            # A drifted citation is not an adjudication: the symbol under the node was
            # rewritten, and the bullet has to be re-read against it. So these go straight onto
            # the worklist and back into the drain, and the `recheck` agent is asked only about
            # the rows that are genuinely a judgement — is this uncovered unit a unit at all.
            self.logger.info(
                "%d node(s) cite source that moved or changed under them; requeueing",
                len(coverage.regrounding),
                extra={"activity": True},
            )
            return Continue(
                self.call(record, self.ctx.worklist_path, None, coverage.regrounding),
                self.select,
                rnd=rnd,
                rescan=coverage.rescan_round,
                refuels=refuels,
            )
        return Continue(
            coverage, self.recheck, rnd=rnd, rescan=coverage.rescan_round, refuels=refuels
        )

    def recheck(self, rnd: int = 0, rescan: int = 0, refuels: int = 0) -> Continue:
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
            "main/prompts/recheck-coverage.md",
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
            result,
            self.seed_recheck,
            discovered=result.discovered,
            rnd=rnd,
            rescan=rescan,
            refuels=refuels,
        )

    def seed_recheck(
        self, discovered: list[dict], rnd: int = 0, rescan: int = 0, refuels: int = 0
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
            refuels=refuels,
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



__all__ = ["MAX_RESCAN_ROUNDS", "MAX_STALL_ROUNDS", "OkfBuilder"]
