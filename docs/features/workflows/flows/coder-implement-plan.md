---
type: flow
slug: coder-implement-plan
title: Coder implement-plan flow
status: implemented
---

# Coder implement-plan flow

`implement-plan` turns a reviewed prose plan into a durable, dependency-ordered sequence of
verified commits. It is a standalone Coder flow rather than a mode of the epic/story loop:

```bash
workhorse-coder run implement-plan --params '{
  "plan_path": "/absolute/path/to/implementation-plan.md"
}'
```

The workflow checkpoints the exact plan text, records its SHA-256 digest, and gives a planning-only
agent turn permission to inspect—but not edit—the repository. That turn returns typed task packets.
Deterministic validation rejects duplicate or cyclic identities, unknown dependencies, unordered
overlapping ownership, unsafe or whole-repository path ownership, shell/Git verification entry
points, missing commands, and invalid Conventional Commit subjects before an implementation turn
can edit files. Other argv-based checks remain trusted plan input; this flow is not a command
sandbox.

The validated `PreparedPlan`, current packet index, completed commit list, and expected `HEAD` travel
as state parameters, so they are the checkpointed execution authority. `worklist.json` is a
rebuildable operator projection of those values. Selection, verification, commit, publication, and
completion never read its task payloads or statuses back to steer execution.

Each packet then follows one checkpointed loop:

1. Resume or implement the packet within its declared paths.
2. Reject any changed path outside that ownership boundary.
3. Run the packet's argv-based verification commands without a shell.
4. Give deterministic failures to a bounded repair turn and rerun the same gate.
5. Run repository hooks and commit only the declared paths, with an opaque run-scoped plan-task
   trailer.
6. Push the current branch without force and verify the remote head.
7. Mark the packet done only after remote verification; then select a dependency-ready packet.

Publication is deliberately **incremental, not transactional**. Every non-final packet reaches
origin after its own clean committed-tree verification. The final aggregate gate can therefore stop
the last packet without retracting earlier independently verified commits. Plans that require
all-or-nothing publication need a separate integration-branch/PR policy rather than this flow.

If the process stopped after `git commit` but before the next checkpoint, the trailer lets the
selector rediscover `HEAD`. Recovery accepts it only when it is the single direct child of the
checkpointed parent, has the exact packet-derived message, and changes only packet-owned paths. A
crash after push is idempotent too: publication accepts the remote at the expected parent or already
at the exact packet commit. The complete aggregate repository gate runs against the fully committed
candidate before the last packet is pushed. The terminal state then verifies the tested `HEAD` is
the remote branch head and writes a completion manifest under the private run directory.

## Safety boundaries

- The checkout must be clean, on a branch, and synchronized exactly with a readable
  `origin/<branch>` when the run starts.
- The source plan is an immutable authority. A source digest change blocks selection; it never
  silently mixes two revisions.
- A packet may not own `.agents` or any directory that contains an in-repository source plan, so an
  ignored/private plan cannot enter a scoped commit accidentally.
- Agent turns receive plan content through their prompt, not filesystem access to the run directory.
- Planning turns must leave the checkout unchanged. Implementation/repair turns may leave only
  packet-owned edits and may not move `HEAD`, change the active branch, alter origin, or change the
  effective Git configuration, hooks, excludes, or attributes. Verification commands must preserve
  the same content fingerprint and refs.
- Deterministic workflow nodes own the accepted commit and push. A recovered or new commit must have
  the checkpointed parent and an owned non-empty diff. Its clean committed tree reruns the packet
  verification in a detached temporary worktree before every push; the final committed tree
  additionally runs the aggregate gate in the same isolated form.
- A failed packet is blocked and stops the run; dependants never run.
- Pushes are ordinary fast-forward pushes. A rejected push requires explicit reconciliation and a
  fresh validation pass; the workflow never force-pushes. Fetch and push URLs must resolve to one
  credential-free endpoint identity so remote verification observes the destination publication
  actually used without checkpointing URL userinfo.
- Repository commit-gating hooks (`pre-commit`, `prepare-commit-msg`, and `commit-msg`) remain
  authoritative. Rejection stops the task; hook mutations must leave a clean, owned candidate that
  passes committed-tree verification. Side-effect hooks such as `post-commit` do not run for the
  workflow-owned commit, so only the later publication state can push it.
- Replacement refs are forbidden and identity-sensitive commit inspection disables replacement
  objects. Git controls are resolved through Git's own `--git-path` rules, including linked
  worktrees, then fingerprinted for the run.
- Task details and plan prose stay in ignored run artifacts/checkpoints. Public Git history receives
  only a deterministic neutral Conventional Commit subject and an opaque random-run task key—not the source
  path, task id, title, or plan digest.

This is a **trusted-agent workflow, not an operating-system sandbox**. The configured agent CLI has
the same host and network authority as every other Coder turn. The checks above prevent Workhorse
from accepting, committing, or continuing after observable unauthorized repository mutation. They
cannot retract an external side effect a malicious or compromised process has already issued. Runs
requiring containment must execute the agent in a separately isolated checkout/container with
publication credentials unavailable to agent processes.

The first version is intentionally sequential and controls one repository/worktree. It does not
parallelize independent packets, create auxiliary worktrees, rewrite a changed plan, poll CI, or
coordinate packets across several repositories. Those require explicit integration and replan
policies rather than extensions to the generic `WorkList` primitive.

## Verification

- `workflows/tests/coder/implement_plan/test_flow.py`
- `workflows/tests/coder/implement_plan/test_validation.py`
- `workflows/tests/coder/implement_plan/test_repository_safety.py`
- `workflows/tests/coder/implement_plan/test_resume.py`
- `workflows/src/workhorse_workflows/coder/implement_plan/flow.py`