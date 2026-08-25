"""The live-app walk as a state machine — the port of `okf-builder/workflow.yaml`'s
`flows.walkthrough-web` (19 nodes, lines 466-729).

Once the code-derived book is complete, walk the running app the way a user would —
entering at the documented front door and moving by clicking, never by URL — to prove the
book against what actually renders and heal it from what it sees. Web-app-ness and the
whole launch recipe are read out of the book by `detect_webapp`, which is what makes this
flow standalone-invokable against a book an earlier run built.

Nineteen nodes become six states plus one private helper, and the collapses are the ones
`author` settled:

* all six `type: branch` nodes — `gate_webapp`, `decide_boot`, `decide_browser`,
  `guard_wt_budget`, `decide_wt_item`, `decide_wt_checkpoint` — read a value the node
  directly above them had just produced. Each is an `if` in its producer.
* `guard_wt_rounds` is a threshold on a counter, so it is two lines at the top of the
  state it guards, and the counter is a state parameter rather than a run-global var.
* `teardown_app` → `teardown_browser` → `wt_done`, the mandatory tail every exit routed
  through, is `_finish`. The YAML expressed "always reap" as graph shape: five branches
  pointed at `teardown_app` so that no arm could forget. A method every terminal calls is
  the same guarantee with the arms visible at the point of decision — and because the
  pgids arrive as **state parameters**, a walk resumed from the middle of the drain can
  still reap what an earlier process started, which the YAML's run-global vars also did.

Divergences from the YAML, all deliberate:

* the `is_webapp` / `boot_ok` / `browser_ok` / `over_budget` / `has_item` /
  `checkpoint_clean` outputs were `"yes"`/`"no"` **strings**, because a YAML branch
  compares text. They are `bool` on the models.
* `detect_webapp` emitted `round: 0` to reset the walk's round cap, because a `var` is
  global to a run and the main graph's `round` would otherwise have leaked in. The walk's
  round is a parameter of `checkpoint` here, so it starts at 0 by construction.
* `refuel: done_count` on `select_wt` has no counterpart: pyflow has no gas tank, and the
  transition budget is what bounds the machine. The drain costs four transitions per item.
* the two boot scripts' `--teardown` sentinel is gone (see `walkthrough_web/nodes/stack.py`).
* `select_wt` was called without `done_baseline`, so its `max_items` cap counted `done`
  over the whole file — a *lifetime* cap, not a per-run one, unlike the main graph's.
  Preserved exactly: this call passes no baseline either. It is a real difference between
  the two drains and it is the YAML's, not the port's.
"""
from __future__ import annotations

from workhorse.pyflow import Continue, Done, NodeNotRunError, Workflow
from workhorse_workflows.okf_builder.shared.checkpoint import checkpoint_book
from workhorse_workflows.okf_builder.shared.schemas import WalkTurn, WebApp
from workhorse_workflows.okf_builder.shared.worklist import record, select_item
from workhorse_workflows.okf_builder.walkthrough_web.nodes import (
    boot_app,
    boot_browser,
    detect_webapp,
    seed_walkthrough,
    teardown_app,
    teardown_browser,
)

#: How many fixup re-drains the walk gets before it gives up and reaps the app. Lower than
#: the build's own bound on purpose — the app is up and costing something while this loops.
MAX_WALK_ROUNDS = 3


class WalkthroughWeb(Workflow):
    """Walk a web service against its running app, and heal the book from what renders.

    Runnable on its own (`workhorse-okf-builder run walkthrough-web`) or reached from the
    build once coverage is complete. Nothing here is passed down from the build: the
    service name, the docs root and the item ceiling are the only inputs, and every path
    is re-derived from the book.
    """

    #: Which `<features-root>/<service>` book to walk — ostler resolves the features root,
    #: so a repo that moved it is followed. `null` in the YAML's `vars`, `""`
    #: here, because an input is typed — a walk with no service detects no app and skips.
    service: str = ""
    #: The docs repo root; `""` walks up from `repo_dir` via `find_docs_root`.
    docs_path: str = ""
    #: The source subtree, defaulting to `service`.
    source_path: str = ""
    #: Per-walk investigation ceiling. 0 = walk to convergence.
    max_items: int = 0

    def setup(self) -> WebApp:
        """Read the walk's whole setting out of the book.

        `detect_webapp`, which is `setup` rather than a state because every state below
        reads its paths and none of them decides one. It is also the flow's gate: a
        service that documents no `screen` surface comes back `is_webapp=False` and
        `start` ends the walk before anything is booted.
        """
        return self.call(detect_webapp, self.docs_path, self.service, self.source_path)

    def labels(self) -> dict[str, str]:
        """Which target the walk is on, and how far along.

        The YAML had no `labels:` block on the flow — a flow inherited the run's, which
        pointed at the *main* graph's `select_item` and therefore went stale for the whole
        walk. Reading the walk's own pick is what the labels were for.
        """
        labels = {"service": self.service}
        try:
            pick = self.output(select_item)
        except NodeNotRunError:
            return labels
        return {**labels, "work_id": pick.item_target, "progress": pick.progress}

    # --- bring-up -----------------------------------------------------------

    def start(self) -> Continue | Done:
        """Gate on the book, bring the app and the browser up, then seed the walk.

        `gate_webapp` + `boot_app` + `decide_boot` + `boot_browser` + `decide_browser` +
        `seed_walkthrough`. One state, because a half-booted stack is not a place to
        resume *into*: both boots are idempotent (each adopts an endpoint that already
        answers rather than double-binding), so re-entering this state after a crash
        re-establishes the same stack instead of a second one.

        The two fail-soft exits keep the YAML's asymmetry, which is not an oversight:
        `decide_boot` "no" goes straight to `wt_done` because `boot_app` already reaped
        whatever it spawned before reporting failure, while `decide_browser` "no" goes
        through the teardown tail because by then an app *is* up.
        """
        if not self.ctx.is_webapp:
            self.logger.info(
                "%s documents no screen surfaces — nothing to walk, skipping cleanly",
                self.service or "(no service)",
            )
            return Done(self.ctx)

        boot = self.call(
            boot_app,
            self.ctx.launch_cmd,
            self.ctx.entry_url,
            self.ctx.health_path,
            self.ctx.app_cwd,
            self.ctx.repo_root,
            self.ctx.app_identity,
            self.ctx.boot_timeout,
        )
        if not boot.boot_ok:
            self.logger.warning(
                "the app would not come up — walking nothing. `boot_app` reaped what it "
                "spawned, so there is nothing to tear down"
            )
            return Done(boot)

        browser = self.call(boot_browser, self.ctx.cdp_url, self.ctx.repo_root)
        if not browser.browser_ok:
            self.logger.warning(
                "no CDP browser — there is nothing to walk with, but the app is up and "
                "must still be reaped"
            )
            return self._finish(boot.app_pgid, browser.browser_pgid)

        seeded = self.call(
            seed_walkthrough, self.ctx.wt_worklist_path, self.service, self.ctx.repo_root
        )
        return Continue(
            seeded,
            self.pick,
            app_pgid=boot.app_pgid,
            browser_pgid=browser.browser_pgid,
            entry_url=boot.entry_url,
            cdp_url=browser.cdp_url,
        )

    # --- the drain ----------------------------------------------------------

    def pick(
        self,
        app_pgid: str,
        browser_pgid: str,
        entry_url: str,
        cdp_url: str,
        rnd: int = 0,
    ) -> Continue | Done:
        """Take the next journey or screen, or converge.

        `select_wt` + `guard_wt_budget` + `decide_wt_item`. The runtime handles ride along
        as parameters rather than living on `self.ctx` because the stack is not part of
        the *setting* — it is what this run brought up, and it is what this run has to put
        back down from wherever it stops.
        """
        pick = self.call(select_item, self.ctx.wt_worklist_path, self.max_items)
        if pick.over_budget:
            self.logger.warning(
                "walk ceiling of %d reached with %d still pending — reaping the app and "
                "leaving the rest for a resume",
                self.max_items,
                pick.pending_count,
            )
            return self._finish(app_pgid, browser_pgid)
        if not pick.has_item:
            return Continue(
                pick,
                self.checkpoint,
                app_pgid=app_pgid,
                browser_pgid=browser_pgid,
                entry_url=entry_url,
                cdp_url=cdp_url,
                rnd=rnd,
            )
        return Continue(
            pick,
            self.walk,
            current_item=pick.current_item,
            item_kind=pick.item_kind,
            item_target=pick.item_target,
            item_context=pick.item_context,
            progress=pick.progress,
            app_pgid=app_pgid,
            browser_pgid=browser_pgid,
            entry_url=entry_url,
            cdp_url=cdp_url,
            rnd=rnd,
        )

    def walk(
        self,
        current_item: dict,
        item_kind: str,
        item_target: str,
        item_context: str,
        app_pgid: str,
        browser_pgid: str,
        entry_url: str,
        cdp_url: str,
        progress: str = "",
        rnd: int = 0,
    ) -> Continue:
        """Drive one journey or screen against the running app.

        A state holding nothing but the turn — the checkpoint is written *before* a state
        runs, so keeping the worklist write downstream is what makes a resume re-record
        rather than re-walk. `power: high` because this one reads the book, drives a real
        browser, compares what renders against what is written, and heals the difference.
        """
        where = f"walking {item_kind} {item_target}"
        self.logger.info(
            "%s%s", where, f" · {progress}" if progress else "", extra={"activity": True}
        )
        result = self.agent(
            "walkthrough_web/prompts/walkthrough-web.md",
            returns=WalkTurn,
            power="high",
            cwd=self.ctx.repo_root,
            add_dirs=[self.ctx.repo_root],
            args={
                "item_kind": item_kind,
                "item_target": item_target,
                "item_context": item_context,
                "service": self.service,
                "features_root": self.ctx.features_root,
                "repo_root": self.ctx.repo_root,
                "entry_url": entry_url,
                "screenshots_dir": self.ctx.screenshots_dir,
                "cdp_url": cdp_url,
            },
        )
        return Continue(
            result,
            self.mark,
            current_item=current_item,
            discovered=result.discovered,
            app_pgid=app_pgid,
            browser_pgid=browser_pgid,
            entry_url=entry_url,
            cdp_url=cdp_url,
            rnd=rnd,
        )

    def mark(
        self,
        current_item: dict,
        discovered: list[dict],
        app_pgid: str,
        browser_pgid: str,
        entry_url: str,
        cdp_url: str,
        rnd: int = 0,
    ) -> Continue:
        """Close the item the turn walked and open whatever it revealed. `record_wt`."""
        recorded = self.call(
            record, self.ctx.wt_worklist_path, current_item, discovered
        )
        return Continue(
            recorded,
            self.pick,
            app_pgid=app_pgid,
            browser_pgid=browser_pgid,
            entry_url=entry_url,
            cdp_url=cdp_url,
            rnd=rnd,
        )

    # --- convergence + the mandatory tail -----------------------------------

    def checkpoint(
        self,
        app_pgid: str,
        browser_pgid: str,
        entry_url: str,
        cdp_url: str,
        rnd: int = 0,
    ) -> Continue | Done:
        """The mechanical gate, then either the phase is done or one more fixup drain.

        `wt_checkpoint` + `decide_wt_checkpoint` + `guard_wt_rounds` + `seed_wt_fixup`.
        The walk's checkpoint calls the same node the build's does with its stall-detection
        parameters left at their defaults — the YAML passed three of the five arguments
        here and five there, and `checkpoint.py` defaulted the rest. A stalled walk is
        bounded by `MAX_WALK_ROUNDS` instead, which is the counter the YAML bounded too.
        """
        result = self.call(
            checkpoint_book, self.ctx.repo_root, self.ctx.features_root, rnd
        )
        if result.checkpoint_clean:
            self.logger.info("the walked book is clean and the drain is dry — walk done")
            return self._finish(app_pgid, browser_pgid)
        if result.round >= MAX_WALK_ROUNDS:
            # Give up fast: the app is up and costing something, and a walk that cannot
            # get doctor clean in three drains is not going to on the fourth.
            self.logger.warning(
                "walk fixup round %d reached the cap of %d with doctor still dirty — "
                "reaping the app and leaving the findings for the build",
                result.round,
                MAX_WALK_ROUNDS,
            )
            return self._finish(app_pgid, browser_pgid)
        self.call(record, self.ctx.wt_worklist_path, None, result.fixup_items)
        return Continue(
            result,
            self.pick,
            app_pgid=app_pgid,
            browser_pgid=browser_pgid,
            entry_url=entry_url,
            cdp_url=cdp_url,
            rnd=result.round,
        )

    def _finish(self, app_pgid: str, browser_pgid: str) -> Done:
        """Reap what this walk started, whichever way it ended. `teardown_app` +
        `teardown_browser` + `wt_done`.

        Every terminal above routes through here, which is the YAML's mandatory tail read
        as a method. Both teardowns are no-ops on an empty pgid — an adopted app or an
        adopted browser is something this run did not spawn and therefore does not kill —
        so the skip paths can call it unconditionally.

        The `Done` value is the detection: what the parent build can learn from a walk is
        whether there was an app to walk at all.
        """
        self.call(teardown_app, app_pgid, self.ctx.stop_cmd, self.ctx.app_cwd)
        self.call(teardown_browser, browser_pgid)
        return Done(self.ctx)


__all__ = ["MAX_WALK_ROUNDS", "WalkthroughWeb"]
