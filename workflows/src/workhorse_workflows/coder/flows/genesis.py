"""Genesis as a state machine — the port of `coder/workflow.yaml`'s `flows.genesis`
(18 nodes, lines 4104-4366).

It turns a directory into something the author and coder workflows can both stand on: a
git repo with a commit, an `agents.yml` carrying a `workspace:` block, farrier's packs and
scaffolds installed, and a service skeleton with its marker file. It is never sequenced by
the main loop — it produces the preconditions the main loop *assumes*, and is entered
directly.

The shape is a straight line with two skip-ahead branches at the front and a bounded
repair loop at the back::

    classify → [git init] → agents.yml → [skeleton] → farrier → [conventions]
             → (verify → fix)* → done

Eighteen nodes become eight states, and every node that disappeared was a branch. All five
`type: branch` nodes read a value the node directly above them had just produced —
`decide_target` reads `resolve_target`'s `target_ok`, `decide_farrier` reads
`install_farrier`'s `farrier_ok`, and so on. That is `if` written across two nodes because
a script cannot route. `incr_genesis` disappears too: the rework count is a state
parameter, which is the whole of what the `incr` call node did.

`decide_genesis` and `decide_skeleton` are the two that fold *forward* rather than back:
each reads a field of the classification (`target_state`, `service_state`) that was
produced several states earlier, so the collapse puts them at the end of the state that
precedes their target rather than the one that produced their input. Repo state and
service state are separate questions on purpose — an established monorepo is exactly where
a new service gets added, so "the repo exists" must not short-circuit the build.

`genesis_failed`, a `type: fail` node reached from three branches, becomes three
`raise WorkflowFailed(...)` at the sites that decided to fail, each carrying the reason the
node reported. The YAML's run ends with "reached genesis_failed" and the reason only in a
log line.

**GENESIS CARRIES ZERO STACK KNOWLEDGE**, and that survives the port unchanged. Every
stack-specific value — `packs`, `scaffolds`, `init_cmd`, `marker`, `markers` — is an input
written through verbatim. `scripts/check_public.py` asserts no base workflow may depend on
the private overlay, and the stack packs live there; a base flow that knew `go` meant
`go.mod` would be a base flow that knows the overlay's contents.

Divergences from the YAML, all deliberate:

* the `*_ok` / `*_valid` outputs were `"yes"`/`"no"` **strings**, because a YAML branch
  compares text. They are `bool` on the models; nothing on disk carried the strings.
* `max_genesis_reworks` was declared as a var *and* re-typed as the literal `"2"` inside
  `guard_genesis`, with the comment "literal so no Jinja in branch". There is one value
  here, `MAX_REWORKS`, and the guard reads it — the duplication existed only because the
  YAML's branch nodes could not evaluate a template.
* `genesis_rework_count: {value: 0}` was seeded in `vars` rather than left to the counter
  node, because `guard_genesis` reads `.value` on the first validation failure, before
  `incr_genesis` has ever run. A state parameter has a declared default, so the seeding
  problem does not exist to solve.
* `git_init` was passed `target_state` as its second argument; `genesis-git-init.py`
  documents the parameter and never reads it. It is omitted, which is faithful rather than
  a narrowing — the same call is made either way.
* the two agent nodes' `default: {status: blocked}` is kept, on the models rather than at
  the callsite: neither reply is branched on, and `validate_genesis` running again is the
  only honest reading of whether a repair worked.
* the comma-separated inputs stay `str` here and are split before reaching a node. That is
  the operator-facing contract exactly as documented — `--params '{"packs": "go",
  "scaffolds": "shared-docs:docs,go-service:api"}'` — and typing them `list[str]` would
  break every recorded invocation.
* the `validate_genesis` node's state is called **`verify`**, not `validate`. `Workflow`
  is a pydantic model, and state discovery skips every name on `dir(Workflow)` — which
  includes pydantic v1's deprecated `validate`, `json`, `dict`, `copy` and `schema`
  aliases. A state named `validate` is therefore silently not a state, and the run only
  finds out when a transition names it. This is the second reserved-name collision the
  coder port hit (see `dream.py` for `run_dir`) and both are in the progress ledger; the
  rename is workflow-side and costs nothing here, since no run has ever checkpointed on
  the name.
* `refuel: target_dir` on `resolve_target` has no counterpart: pyflow has no gas tank. The
  flow is linear apart from a repair loop bounded at two, so the transition budget is not
  in question here; it is recorded in the progress ledger as a driver-level gap rather
  than worked around per flow.
"""
from __future__ import annotations

from typing import ClassVar

from workhorse.pyflow import (
    Continue,
    Done,
    NodeNotRunError,
    Workflow,
    WorkflowFailed,
)
from workhorse_workflows.coder.nodes.genesis import (
    genesis_git_init,
    init_skeleton,
    install_farrier,
    resolve_genesis_target,
    validate_genesis,
    write_agents_yml,
)
from workhorse_workflows.coder.schemas.genesis import (
    ConventionsResult,
    FixResult,
    TargetClassification,
)


class Genesis(Workflow):
    """A directory in, a repo the main loop will accept out.

    Safe to re-run: the classification at the front is what makes that true, routing an
    already-initialised repo to a config refresh instead of scaffolding over live work.
    """

    #: Required — the path to the repo to create. `resolve_genesis_target` fails the flow
    #: when it is empty or names something unusable.
    target: str = ""
    #: The logical service name, which is also the workspace repo key in `agents.yml`.
    service: str = ""
    #: The repo-relative directory the service lives in (e.g. `"api"`).
    service_root: str = ""
    #: Comma-separated farrier pack ids. Empty means "install nothing", which
    #: `install_farrier` turns into a skip rather than an error.
    packs: str = ""
    #: Comma-separated `"<scaffold-id>:<dir>"` pairs.
    scaffolds: str = ""
    #: The stack's own init command, run verbatim in the service directory.
    init_cmd: str = ""
    #: The file that proves the init worked (e.g. `"go.mod"`).
    marker: str = ""
    #: Comma-separated service markers for `agents.yml`. Falls back to `marker`.
    markers: str = ""
    #: Workflows to register in `agents.yml`.
    workflows: str = "coder"
    #: Agent backends to enable. `farrier install` hard-exits with none.
    assistants: str = "claude"

    #: Repair rounds before the run is failed — the literal `"2"` `guard_genesis`
    #: compared against.
    #:
    #: `ClassVar`, so it is not an operator-settable input, and that is the faithful
    #: reading: the YAML declared `max_genesis_reworks: "2"` as a var *and* re-typed the
    #: literal in the guard, because a branch node cannot evaluate a template. The var
    #: was therefore inert — `--params '{"max_genesis_reworks": "5"}'` changed nothing.
    #: Promoting it to a live input would be an addition, and additions are not this
    #: loop's.
    MAX_REWORKS: ClassVar[int] = 2

    # --- classification -----------------------------------------------------

    def start(self) -> Continue:
        """Classify the target before anything mutates it.

        `resolve_target` + `decide_target` + `decide_genesis`. The fail-fast matters: with
        no target every script below no-ops with a note and the run still reaches the
        conventions agent, burning a model call to discover there is nothing there.

        An existing repo skips `git init` alone. It still flows through the config refresh
        and on to the service-level decision, because a long-established monorepo is
        exactly where a *new* service gets added.
        """
        found = self.call(
            resolve_genesis_target, self.target, self.service, self.service_root, self.marker
        )
        if not found.ok:
            raise WorkflowFailed(found.note or "no usable genesis target")
        if found.target_state == "existing":
            return Continue(found, self.config)
        return Continue(found, self.git_init)

    # --- the build ----------------------------------------------------------

    def git_init(self) -> Continue:
        """`git init` and one initial commit — the first mutating step, and it must be.

        ostler's `find_root` walks *up* for `.git`/`docs/`/`ostler.yml`/`agents.yml`. A
        brand-new directory matches none of them, so any ostler call made before this
        binds to an ancestor repo silently: ids from the parent's registry, docs into the
        parent's tree, no error anywhere. `verify` asserts the binding landed, because
        that misbind is undetectable after the fact.
        """
        result = self.call(genesis_git_init, self._target().target_dir)
        return Continue(result, self.config)

    def config(self) -> Continue:
        """Merge the service into `agents.yml`, then decide whether it needs building.

        `write_agents_yml` + `decide_skeleton`. The `workspace:` block is what lets the
        planner target the service at all, and `scaffolds` is written here because
        `farrier scaffold <id>` refuses an id that is not enabled in `agents.yml` — the
        farrier step below would render nothing without it.

        The skeleton decision is keyed on the **service**, not the repo: `go mod init` and
        friends fail or clobber when re-run over a live service, so an existing one goes
        straight to the farrier refresh.
        """
        found = self._target()
        result = self.call(
            write_agents_yml,
            found.target_dir,
            found.service,
            self._split(self.packs),
            self.service_root,
            self._split(self.markers or self.marker),
            self._split(self.workflows),
            self._split(self.scaffolds),
            self._split(self.assistants),
        )
        if found.service_state == "existing":
            return Continue(result, self.farrier)
        return Continue(result, self.skeleton)

    def skeleton(self) -> Continue:
        """Run the stack's native init tooling, and assert it left its marker behind.

        Ordered *before* farrier, which is load-bearing. Scaffolds seed files into the
        service directory (a `.gitignore`), and stack generators refuse to write into a
        directory that already has any: observed live, the `react-router-web` scaffold
        seeded `web/.gitignore` and `npm create react-router` then aborted with
        "Destination directory contains files that would be overwritten". Native init
        first, scaffolds over the top — farrier never clobbers a file the repo already
        owns, so seeding after is safe while seeding before is not.
        """
        result = self.call(
            init_skeleton, self._target().target_dir, self.service_root, self.init_cmd, self.marker
        )
        return Continue(result, self.farrier)

    def farrier(self) -> Continue:
        """Install the packs and render the scaffolds, then decide what earned the agent.

        `install_farrier` + `decide_farrier` + `decide_skeleton_ok`. Both branches route to
        the same place, and both are about *not* spending an agent turn on a repo that
        cannot benefit from one:

        * a failed install means no skills and no docs tree — there is nothing for the
          conventions turn to be conventional *about*;
        * a failed native init must not reach it either. Observed live: `npm create
          react-router` produced no `package.json`, the flow walked on, and the agent —
          handed an empty service directory and asked to make it conventional — fabricated
          a placeholder tree that looked like a service but was not one.

        A skeleton that never ran leaves nothing to read, and that is the config-refresh
        path: conventions are not re-applied to a live service. It reads as "not ok" here
        exactly as the YAML's undefined `skeleton_ok` fell to `decide_skeleton_ok`'s
        `default:` arm.
        """
        result = self.call(
            install_farrier,
            self._target().target_dir,
            self._split(self.scaffolds),
            not self._split(self.packs),
        )
        if not result.ok or not self._skeleton_ok():
            return Continue(result, self.verify)
        return Continue(result, self.conventions)

    def conventions(self) -> Continue:
        """Make the repo conventional for its stack, guided by the skills farrier installed.

        The one genuinely judgement-shaped step, and structure only: there are no stories
        yet, so any product code written here is scope nobody asked for. `power: low`
        because the skills carry the conventions — the turn applies them rather than
        deciding them.
        """
        found = self._target()
        result = self.agent(
            "prompts/apply-genesis-conventions.md",
            returns=ConventionsResult,
            power="low",
            cwd=found.target_dir,
            args={
                "target_dir": found.target_dir,
                "service_root": self.service_root,
                "marker_path": self._marker_path(),
            },
        )
        return Continue(result, self.verify)

    # --- the bounded repair loop --------------------------------------------

    def verify(self, reworks: int = 0) -> Continue | Done:
        """Assert every precondition the main loop assumes, and repair or fail.

        `validate_genesis` + `decide_valid` + `guard_genesis`. Genesis's postcondition *is*
        the main loop's precondition, and they share one assertion implementation
        (`coder.contract`) so they cannot drift apart silently.

        `reworks` is the counter, and being a state parameter it is also the checkpoint: a
        resume picks up with the same budget spent, which is what the YAML's seeded
        `genesis_rework_count` var was reaching for.
        """
        report = self.call(
            validate_genesis,
            self._target().target_dir,
            self.service_root,
            self._split(self.markers or self.marker),
        )
        if report.valid:
            return Done(report)
        if reworks >= self.MAX_REWORKS:
            raise WorkflowFailed(
                f"genesis still invalid after {reworks} repair round(s): {report.errors}"
            )
        return Continue(report, self.fix, reworks=reworks)

    def fix(self, reworks: int) -> Continue:
        """Hand the validator's errors to a repair turn, then validate again.

        A state of its own, holding nothing but the turn: the checkpoint is written before
        a state runs, so re-validating downstream is what makes a resume cheap. `power:
        high` because a broken genesis is a diagnosis problem — the errors name symptoms,
        and the fix is usually re-running a tool that failed for a reason not stated.

        Its reply is not branched on. `verify` running again decides.
        """
        found = self._target()
        report = self.output(validate_genesis)
        result = self.agent(
            "prompts/fix-genesis.md",
            returns=FixResult,
            power="high",
            cwd=found.target_dir,
            args={
                "target_dir": found.target_dir,
                "genesis_errors": report.errors,
                "genesis_warnings": report.warnings,
            },
        )
        return Continue(result, self.verify, reworks=reworks + 1)

    # --- helpers ------------------------------------------------------------

    def _target(self) -> TargetClassification:
        """The classification every state below reads, exactly as the YAML re-read it.

        Six nodes carried `get_node_output('resolve_target', 'target_dir')`; this is that
        read, once, with a name. It is a method rather than threaded state because the
        classification is a fact about the run, not a value any state hands to the next.
        """
        return self.output(resolve_genesis_target)

    def _skeleton_ok(self) -> bool:
        """Whether the skeleton step ran *and* produced its marker.

        A service that already existed skipped `skeleton` entirely, so there is no output
        to read — the YAML left `skeleton_ok` undefined there and its branch took the
        `default:` arm. This returns False for the same case, for the same reason.
        """
        try:
            return self.output(init_skeleton).ok
        except NodeNotRunError:
            return False

    def _marker_path(self) -> str:
        """The marker the skeleton step asserted, or `""` when it did not run."""
        try:
            return self.output(init_skeleton).marker_path
        except NodeNotRunError:
            return ""

    @staticmethod
    def _split(value: str) -> tuple[str, ...]:
        """A comma-separated operator input as the sequence the nodes take.

        Blank entries are dropped, so a trailing comma is not a pack named `""`.
        """
        return tuple(part.strip() for part in value.split(",") if part.strip())


__all__ = ["Genesis"]
