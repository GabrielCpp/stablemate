"""Genesis as a state machine — the port of `coder/workflow.yaml`'s `flows.genesis`
(18 nodes, lines 4104-4366).

It turns a directory into something the author and coder workflows can both stand on: a
git repo with a commit, an `agents.yml` carrying a `workspace:` block, farrier's packs and
scaffolds installed, and a service skeleton with its marker file. It is never sequenced by
the main loop — it produces the preconditions the main loop *assumes*, and is entered
directly.

Genesis is pure bootstrapping: every state below is deterministic tooling, with no agent
turn anywhere in the flow. The two agent turns the YAML carried (a "make it conventional"
pass and a repair turn) are gone — there is no product code, no story and nothing
judgement-shaped for an agent to do at this stage, and a repair turn that could only guess
at a tooling failure was never more than a second, unaccountable roll of the same dice
`verify` already failed. A target that fails validation now fails the run directly.

The shape is a straight line with two skip-ahead branches at the front::

    classify → [git init] → agents.yml → [skeleton] → farrier → verify → done

Eighteen nodes become six states, and every node that disappeared was a branch. All five
`type: branch` nodes read a value the node directly above them had just produced —
`decide_target` reads `resolve_target`'s `target_ok`, `decide_farrier` reads
`install_farrier`'s `farrier_ok`, and so on. That is `if` written across two nodes because
a script cannot route.

`decide_genesis` and `decide_skeleton` are the two that fold *forward* rather than back:
each reads a field of the classification (`target_state`, `service_state`) that was
produced several states earlier, so the collapse puts them at the end of the state that
precedes their target rather than the one that produced their input. Repo state and
service state are separate questions on purpose — an established monorepo is exactly where
a new service gets added, so "the repo exists" must not short-circuit the build.

`genesis_failed`, a `type: fail` node reached from several branches, becomes
`raise WorkflowFailed(...)` at the site that decided to fail, carrying the reason the node
reported.

**GENESIS CARRIES ZERO STACK KNOWLEDGE**, and that survives the port unchanged. Every
stack-specific value — `packs`, `scaffolds`, `init_cmd`, `marker`, `markers` — is an input
written through verbatim. `scripts/check_public.py` asserts no base workflow may depend on
the private overlay, and the stack packs live there; a base flow that knew `go` meant
`go.mod` would be a base flow that knows the overlay's contents.

Divergences from the YAML, all deliberate:

* the `*_ok` / `*_valid` outputs were `"yes"`/`"no"` **strings**, because a YAML branch
  compares text. They are `bool` on the models; nothing on disk carried the strings.
* `git_init` was passed `target_state` as its second argument; `genesis-git-init.py`
  documents the parameter and never reads it. It is omitted, which is faithful rather than
  a narrowing — the same call is made either way.
* the comma-separated inputs stay `str` here and are split before reaching a node. That is
  the operator-facing contract exactly as documented — `--params '{"packs": "go",
  "scaffolds": "shared-docs:docs,go-service:api"}'` — and typing them `list[str]` would
  break every recorded invocation.
* the `validate_genesis` node's state is called **`verify`**, not `validate`. `Workflow`
  is a pydantic model, and state discovery skips every name on `dir(Workflow)` — which
  includes pydantic v1's deprecated `validate`, `json`, `dict`, `copy` and `schema`
  aliases. A state named `validate` is therefore silently not a state, and the run only
  finds out when a transition names it. This is the second reserved-name collision the
  coder port hit, and it is in the progress ledger; the rename is workflow-side and costs
  nothing here, since no run has ever checkpointed on the name.
* `refuel: target_dir` on `resolve_target` has no counterpart: pyflow has no gas tank. The
  flow is a straight line now, so the transition budget is not in question here; it is
  recorded in the progress ledger as a driver-level gap rather than worked around per flow.
"""
from __future__ import annotations

from workhorse.pyflow import (
    Continue,
    Done,
    Workflow,
    WorkflowFailed,
)
from workhorse_workflows.coder.genesis.nodes import (
    genesis_git_init,
    init_skeleton,
    install_farrier,
    resolve_genesis_target,
    validate_genesis,
    write_agents_yml,
)
from workhorse_workflows.coder.shared.schemas.genesis import TargetClassification


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
    #: Comma-separated `"<gate>=<command>"` pairs for the service's `services:` block —
    #: the deterministic gates the dev lane runs after every implement turn (e.g.
    #: `"lint=make lint,test=make test"`). Empty leaves the repo ungated, which the dev
    #: lane skips rather than guesses at.
    gates: str = ""

    # --- classification -----------------------------------------------------

    def start(self) -> Continue:
        """Classify the target before anything mutates it.

        `resolve_target` + `decide_target` + `decide_genesis`. The fail-fast matters: with
        no target every script below no-ops with a note and the run still reaches
        `verify`, failing there instead of quietly building over nothing.

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
            self._split(self.gates),
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
        """Install the packs and render the scaffolds, then move on to validation.

        `install_farrier` + `decide_farrier` + `decide_skeleton_ok`, minus the branch: both
        outcomes used to pick between two agent turns, and there is only one path left now
        that neither turn exists. `verify` is what decides whether the build succeeded.
        """
        result = self.call(
            install_farrier,
            self._target().target_dir,
            self._split(self.scaffolds),
            not self._split(self.packs),
        )
        return Continue(result, self.verify)

    def verify(self) -> Done:
        """Assert every precondition the main loop assumes, and fail if it does not hold.

        `validate_genesis` + `decide_valid` + `guard_genesis`. Genesis's postcondition *is*
        the main loop's precondition, and they share one assertion implementation
        (`coder.shared.contract`) so they cannot drift apart silently.

        There is no repair turn: genesis is pure bootstrapping, and a target that fails
        validation is a tooling problem an agent guessing at the same errors would not have
        fixed more reliably than the tool that already produced them. The operator re-runs
        with corrected params instead.
        """
        report = self.call(
            validate_genesis,
            self._target().target_dir,
            self.service_root,
            self._split(self.markers or self.marker),
        )
        if not report.valid:
            raise WorkflowFailed(f"genesis target is invalid: {report.errors}")
        return Done(report)

    # --- helpers ------------------------------------------------------------

    def _target(self) -> TargetClassification:
        """The classification every state below reads, exactly as the YAML re-read it.

        Six nodes carried `get_node_output('resolve_target', 'target_dir')`; this is that
        read, once, with a name. It is a method rather than threaded state because the
        classification is a fact about the run, not a value any state hands to the next.
        """
        return self.output(resolve_genesis_target)

    @staticmethod
    def _split(value: str) -> tuple[str, ...]:
        """A comma-separated operator input as the sequence the nodes take.

        Blank entries are dropped, so a trailing comma is not a pack named `""`.
        """
        return tuple(part.strip() for part in value.split(",") if part.strip())


__all__ = ["Genesis"]
