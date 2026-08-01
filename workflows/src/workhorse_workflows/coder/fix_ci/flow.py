"""The CI fix loop as a state machine — the port of `coder/workflow.yaml`'s `flows.fix_ci`
(11 nodes, lines 3895-4033).

It is reached from the main graph's epic gate as a `type: flow` node, and standalone as
`workhorse-coder run fix_ci`. Its job is to walk the workspace one repo at a time and, for
each, get the epic branch's CI green — or establish that it cannot be::

    (pick a repo → (poll → fix → push)* )*

Eleven nodes become four states. The three `type: branch` nodes each read a value the node
directly above them had just produced, and `incr_ci_attempts` — a `type: call` on `incr` —
disappears entirely, because the counter is a state parameter now. The two loops share
their states rather than nesting: `poll` returning to `start` is the outer one advancing to
the next repo, and `push` returning to `poll` is the inner one re-reading CI after a fix.

**The repo is a parameter, not the process's cwd.** Every node in the YAML graph carried
`cwd: {{ current_repo_cwd }}`, and `await-pr-checks.py` has a long note explaining that it
must therefore use `Path.cwd()` and specifically *not* `find_repo_root()`. A driver node
has no per-node cwd, so the directory arrives as `repo_dir` — which is what the flow always
meant, and what the `cwd:` field was a mechanism for. The agent turn still takes a real
`cwd`, because there the working directory decides which flavor prompt and which
`CLAUDE.md` the turn sees; that is a genuine use of it, not a path-resolution workaround.

Divergences from the YAML, all deliberate:

* `processed_repos` was a JSON-encoded **string**, round-tripped through
  `json.dumps`/`json.loads` on every hop because a workflow var is a string. It is a
  `list[str]` state parameter here; nothing on disk carried the encoded form.
* `ci_status` and `push_status` stay strings rather than becoming bools, which is a
  divergence from `author`'s treatment of its tri-states. Both have three arms whose
  `default:` — the one a blank value takes — is the *pessimistic* one, and a pair of bools
  cannot express that without inventing a third. Each branch below names the arm a blank
  falls into.
* `select-ci-fix-repo.py` was passed `ci_summary` and `docs_path`; the script comments both
  out as unused. They are omitted from the node, which is faithful rather than a
  narrowing — the same selection is made either way.
* `await-pr-checks.py` was passed `""` for `base_branch`, annotated in the YAML as "not
  used by the script, passed for interface parity". There is no positional interface left
  to keep parity with, so it is gone.
* the `ci_summary` **input** is kept for interface parity and is never read. `poll` always
  runs before `fix` and overwrites the var, so the summary the main graph passes in from
  `await_ci` could never reach the fixer. That is the YAML's behavior, preserved; it is
  recorded in the progress ledger as a finding rather than quietly repaired.
* `ci_attempts` is a **lifetime** budget across every repo, not a per-repo one. The YAML's
  comment says "per repo" and the counter is never reset when `select_ci_repo` advances,
  so the second repo inherits whatever the first spent. Behavior preserved, comment
  corrected here, mismatch recorded in the ledger.
"""
from __future__ import annotations

from typing import ClassVar

from workhorse.pyflow import Continue, Done, NodeNotRunError, Workflow
from workhorse_workflows.coder.shared import paths
from workhorse_workflows.coder.shared.ci import poll_pr_checks, push_ci_fix, select_ci_repo
from workhorse_workflows.coder.shared.story import resolve_workspace_dirs
from workhorse_workflows.coder.shared.schemas.ci import CiChecks, FixCiResult
from workhorse_workflows.coder.shared.schemas.story import WorkspaceDirs


class FixCi(Workflow):
    """Poll a PR's Actions runs, hand a failure to a fixer, push, poll again."""

    #: An explicit workspace repo key. Empty iterates every workspace repo in order.
    repo: str = ""
    #: The full branch name (e.g. `feat/EPIC-X`). Nothing to gate on without it.
    branch: str = ""
    #: A PR number, pinning the poll to one PR. Empty resolves by branch name, which a
    #: branch that has carried more than one PR can resolve wrongly.
    pr_number: str = ""
    #: Accepted for interface parity with the main graph's `type: flow` node, and never
    #: read — the first poll overwrites it before the fixer sees anything. See the module
    #: docstring.
    ci_summary: str = ""
    #: The docs repo root, prepended to the fixer's readable directories. Empty walks up
    #: from `repo_dir`.
    docs_path: str = ""
    #: The `.code-workspace` manifest naming this run's repos. Empty falls back to the
    #: single checkout at `repo_dir` — a one-repo run needs no manifest.
    workspace_file: str = ""


    #: The ambient path inputs — `repo_dir`, `docs_path`, `workspace_file`. The seams
    #: fill each one in for any node or sub-flow that declares a parameter of the same
    #: name and was not passed one; see `Workflow.injects`.
    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    #: `fix → push → poll` cycles before the loop gives up. The YAML's literal `"3"`.
    #: `ClassVar` because `Workflow` is a pydantic model and every annotated class
    #: attribute is otherwise an operator-settable input; a budget the flow owns is not
    #: one, and the YAML did not expose it as a var either.
    MAX_ATTEMPTS: ClassVar[int] = 3

    def setup(self) -> WorkspaceDirs:
        """Every directory the fixer may read: the workspace repos, plus the docs root.

        `resolve_workspace`. It is `setup` rather than a state because nothing decides on
        it — it is read once, by the agent turn, as `add_dirs` — and because a resume
        should not re-derive the workspace it was already driving against.

        The node is the story spine's `resolve_workspace_dirs`, which carries
        `resolve_ci_workspace` as an alias: this flow called the same body under that name
        before `dev` needed it too, and the alias is what keeps an in-flight run resumable
        across the rename.
        """
        return self.call(resolve_workspace_dirs, self.docs_path)

    def start(self, processed: list[str] | None = None, attempts: int = 0) -> Continue | Done:
        """Take the next repo whose CI has not been looked at, or finish.

        `select_ci_repo` + `decide_ci_repo`. A repo joins `processed` the moment it is
        *picked* rather than when its CI settles, so a repo that exhausts the fix budget is
        still not revisited — which is what makes the outer loop terminate.
        """
        pick = self.call(select_ci_repo, self.repo, processed)
        if not pick.has_repo:
            return self._finish("no workspace repo left to check")
        self.logger.info("checking CI for %s in %s", self.branch, pick.repo)
        return Continue(
            pick,
            self.poll,
            repo=pick.repo,
            repo_dir=pick.repo_cwd,
            processed=pick.processed,
            attempts=attempts,
        )

    def poll(
        self, repo: str, repo_dir: str, processed: list[str], attempts: int
    ) -> Continue | Done:
        """Block until this repo's Actions runs settle, then route on the verdict.

        `poll_ci` + `decide_ci` + `guard_ci_attempts`. `unavailable` moves on with
        `passed`, deliberately: offline, CI-less and read-blocked runs are not evidence of
        a broken branch, and treating them as failures would send a fixer at a repo with
        nothing to fix. A blank status lands with `failed`, which is the pessimistic arm
        the YAML's `default:` took.
        """
        checks = self.call(poll_pr_checks, repo_dir, self.branch, self.pr_number)
        if checks.status in ("passed", "unavailable"):
            return Continue(checks, self.start, processed=processed, attempts=attempts)
        if attempts >= self.MAX_ATTEMPTS:
            return self._finish(
                f"CI still red for {self.branch} in {repo} after {attempts} attempt(s): "
                f"{checks.summary}"
            )
        return Continue(
            checks,
            self.fix,
            repo=repo,
            repo_dir=repo_dir,
            processed=processed,
            attempts=attempts,
            summary=checks.summary,
        )

    def fix(
        self, repo: str, repo_dir: str, processed: list[str], attempts: int, summary: str
    ) -> Continue:
        """Diagnose the failing checks and commit a fix on the branch.

        A state of its own, holding nothing but the turn: it is the expensive thing in the
        loop and the checkpoint is written before a state runs, so leaving the push
        downstream is what makes a resume cheap.

        `cwd` is the picked repo, which is what lets workhorse resolve a repo-specific
        flavor override from `<repo>/.agents/flavors/coder/fix-ci.md`. It does **not**
        push: `push` below does, so credential handling stays in one place.
        """
        result = self.agent(
            "prompts/fix-ci.md",
            # medium: reads failing job logs and the diff, and makes a narrow repair —
            # bounded diagnosis rather than design.
            power="medium",
            returns=FixCiResult,
            cwd=repo_dir,
            add_dirs=list(self.ctx.dirs),
            args={"ci_epic": self.branch, "ci_summary": summary},
        )
        return Continue(
            result,
            self.push,
            repo=repo,
            repo_dir=repo_dir,
            processed=processed,
            attempts=attempts,
        )

    def push(
        self, repo: str, repo_dir: str, processed: list[str], attempts: int
    ) -> Continue | Done:
        """Push the fix so GitHub triggers a new run, then poll again.

        `push_ci_fix` + `decide_push_fix` + `incr_ci_attempts`. A fix that cannot be pushed
        can never turn CI green, so a `failed` push ends the loop for this repo rather than
        spending another attempt polling an unmoved PR head — and a blank status lands
        there too, which is the arm the YAML's `default:` took. `unavailable` continues,
        so an offline run still reaches the poll that reports the pass-through.
        """
        outcome = self.call(push_ci_fix, repo_dir, self.branch)
        if outcome.status not in ("pushed", "unavailable"):
            return self._finish(f"could not push the fix for {self.branch} in {repo}")
        return Continue(
            outcome,
            self.poll,
            repo=repo,
            repo_dir=repo_dir,
            processed=processed,
            attempts=attempts + 1,
        )

    def _finish(self, reason: str) -> Done:
        """`fix_ci_done` — the one terminal, reached from three places.

        The YAML's terminal declared no outputs, and the main graph's `fix_ci_result` is
        not branched on. What is handed back is the last CI verdict the loop actually read,
        with `reason` as its summary, because that is the most informative thing available
        at any of the three exits. Before the first poll there is none, and "we never got
        as far as looking" is `unavailable`.
        """
        try:
            status = self.output(poll_pr_checks).status
        except NodeNotRunError:
            status = "unavailable"
        self.logger.info("CI fix loop finished: %s", reason)
        return Done(CiChecks(status=status, summary=reason))


__all__ = ["FixCi"]
