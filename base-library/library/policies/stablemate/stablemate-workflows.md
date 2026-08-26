---
name: stablemate-workflows
description: "The invariants a workhorse workflow is held to, resident in every turn under `workflows/`: a workflow is Python and not YAML, it reads no environment because a value outside the checkpoint makes a resume silently different, and it never gives up — a exhausted repair budget escalates to the operator gate rather than ending the run. Each one constrains a change an agent would otherwise make before it had any reason to go looking."
---

# workflows

The state machines workhorse drives. A workflow is **Python**, not YAML. The YAML
engine is retired — no `workflow.yml`, no `requires:` block, no node-graph
document. Prose describing one is stale; fix it.

## A workflow reads no environment (load-bearing)

`os.environ` / `os.getenv` are **prohibited** anywhere under
`src/workhorse_workflows/`. Everything a node or a state needs is an argument
or a workflow parameter — a field on the `Workflow` subclass, settable with `--param`.
A value read from the environment is in no checkpoint (so a resume silently takes a
different one) and in no telemetry, and `--params` cannot set it.

The process boundary is where the environment belongs, and it is outside that package:
`workhorse/cli/run.py` and `workhorse/supervisor.py` translate `$FOO` into `--params`
once, on the way in. The one allowlisted module is `kit/credentials.py`, and for the
opposite reason — a secret must *never* become a checkpointed `--param`.

```bash
make check-no-env    # from the repo root; also runs as part of `make test`
```

The full rule, including `Workflow.injects` for the ambient paths
(`repo_dir`/`docs_path`/`workspace_file`), is in [README.md](README.md).

## A workflow never gives up — it can only be blocked (load-bearing)

A pyflow state ends one of three ways: `Continue`, `Done`, or `Await`. A repair-budget
exhaustion inside a bounded rework loop — a QA-plan repair, a code-fix lap, a stalled
identical failure — is **not** a fourth way. It escalates to the operator gate (`Await`)
like any other block, checkpointed and resumable, and never ends the run in
`WorkflowFailed` on that ground alone. There is no cap on how many times a story can
bounce back to that gate across resumes — the same "no cap on escalations" the gate
already applied to human mode now applies unconditionally.

The reason is what a give-up used to look like from outside: a story committed behind a
`[QA FAILED — needs manual review]` marker, the run reporting success on the next story
built atop a rejected baseline, and the review nobody stopped to demand never happening.
An `Await` costs the same operator ten minutes it always would have; a give-up spent
those ten minutes anyway; it just spent them after the run had already moved on.

The auto-resolver a block routes through — one shared prompt,
`coder/shared/prompts/resolve-operator.md`, rendered by every lane that gates —
**applies decisions; it does not make them.** It may write `STATUS: ANSWERED` and let
the loop continue only when it can quote the thing that already settles the question — a
record under `<docs-root>/docs/decisions/`, a convention in `AGENTS.md` or an installed
skill, an acceptance criterion in the story's own spec — and it publishes that citation
in the answer and in the run log. A question with a written answer costs a human nothing
to be asked and teaches them nothing when they answer it the way the document already
says.

A question *without* one is theirs by definition, and the resolver escalates: an unwritten
product or scope call, two sources that genuinely conflict, anything needing a credential
or a spend, and every block where the resolver is the interested party (it never narrows
its own QA `covers:`, stamps its own status, or edits its own evidence). "I am not sure" is
an escalation too. The parking half of this rule is untouched — a block it cannot ground
`Await`s, as many times as it takes, and never ends the run.

The place decisions accumulate is `<docs-root>/docs/decisions/`
(`coder/shared/paths.py::decisions_dir`), and answering writes one, so the second run to
hit the same question reads the ruling instead of parking on it again. Every lane caps the
*resolver* rather than the block — `MAX_PLAN_BLOCKS`, `MAX_REVIEW_BLOCKS`, `MAX_QA_BLOCKS`
— and spends that budget on an answer exactly as on an escalation, so a resolver that keeps
applying a rule the block does not clear walks toward a person instead of lapping forever.
The branch, the vocabulary and the argument all live in `coder/shared/resolution.py`.

```bash
make check-no-giveup    # from the repo root; also runs as part of `make test`
```

This guard is narrow: it stops the specific vocabulary of a deleted give-up pattern from
quietly reappearing, not every way the rule could be broken. It does not cover the
resolver-authority half of the rule — that an `answered` arm exists only where the answer
was grounded in something already written, at the `operator_mode` sites in
`author/main/flow.py`, `author/surveyor/flow.py`, `coder/dev/flow.py`,
`coder/review/flow.py`, `coder/qa/flow.py` and `coder/docs/flow.py` — which needs the
control-flow graph, not a grep, same as everything else this check cannot see
structurally. See the script's own docstring before widening it.
