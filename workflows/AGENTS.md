# workflows

The state machines workhorse drives. A workflow is **Python**, not YAML. The YAML
engine is retired — no `workflow.yml`, no `requires:` block, no node-graph
document. Prose describing one is stale; fix it.

## Every directory under `src/workhorse_workflows/` is a workflow, except `kit/` and `new/`

`author/`, `coder/`, `okf_book/`, `research/`, `loop_runner/` — one directory per
workflow, each with the `workflow.py` composition root its console script points at.
A directory beside them that is not a workflow reads as one, and the next agent looks
for the entry point it does not have.

`new/` is the other exception. It holds the `workhorse-new` command and the template
it renders, and its README says so on its first line.

**Code a second workflow also calls goes to `kit/`.** That is where the family-neutral
domain code lives — git, GitHub, workspaces, paths, JSON, external CLIs, QA stacks —
and it is the only shared directory at that level. Inside one workflow the same
rule applies one level down, to `<workflow>/shared/`. The count decides, not the
subject: a module one machine calls belongs to that machine, a module two machines call
moves up.

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
make check-no-env    # from the repo root, on its own
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
make check-no-giveup    # from the repo root, on its own
```

This guard is narrow: it stops the specific vocabulary of a deleted give-up pattern from
quietly reappearing, not every way the rule could be broken. It does not cover the
resolver-authority half of the rule — that an `answered` arm exists only where the answer
was grounded in something already written, at the `operator_mode` sites in
`author/main/flow.py`, `author/surveyor/flow.py`, `coder/dev/flow.py`,
`coder/review/flow.py`, `coder/qa/flow.py` and `coder/docs/flow.py` — which needs the
control-flow graph, not a grep, same as everything else this check cannot see
structurally. See the script's own docstring before widening it.

## A workflow is written after the session that worked (load-bearing)

Aims 8 and 9 of [the constitution](../docs/CONSTITUTION.md) set two rules for every
workflow here. `/vet-proposal` holds a new workflow, a new stage or a new repair loop to
both.

**Attended first.** A process becomes a workflow after an attended session has finished
it at least twice on a real target of the intended size. The proposal cites those
sessions. Their transcripts say which seats the workflow needs, what each seat must see
and what each may touch. A run that does not converge is answered by finishing its
target attended, then folding that session back in. It is not answered by more
machinery around the run.

**One owner, with narrow helpers.** Every loop that repairs work has one owner seat that
holds the whole work and repairs it itself. Code runs the gates between the owner's turns
and opens its next turn on their results: every failure grouped by what was observed, the
logs, and what the toolchain sent. The owner names a side for each group: the work, the
toolchain, a fixture, the environment or the app. Only the groups it names the work's own
come back to it. The rest stop as findings for the level above, and a lap that does not
lower the failures asks the operator. A narrow seat checks one thing or retrieves one
thing for the owner, read-only, and never edits the work. The owner runs on the strongest
model profile the run has. Helpers may run on a cheaper one.

The reason is what the other shapes cost. A narrow node told to repair a page edits the
page, because the page is all it can touch. The okf-book run on a large API spent 87 of
99 hours that way. Its largest causes sat in the test compiler, the fixtures and the
environment, where no page edit could reach them. Each one was found by an attended
session reading the whole lap, and fixed once. A lead seat above batches of narrow
writers did not close that gap. On a web app's book, every batch failed behind the same
missing sign-in fixture, which no batch held, and the lead's finding reached the writers
only as text.

## A prompt is a file, unless it is too small to be one

`self.agent("dev/prompts/implement-plan.md", …)` stays the default spelling. The file is
what a repo's `.agents/flavors/**` override replaces, what `references.missing_references`
reads, and what the AST sweeps under `workflows/tests/` check for output shape, undeclared
variables and existence.

A turn carrying `label=` writes its text at the call site instead. Inline is a short fixed
turn with no skill reference and nothing an operator would flavor. A file is everything
else. `self.agent` refuses a bad label, un-parseable Jinja and a manifest reference
outright. The rest is a judgement call, and it goes the file's way whenever the turn
carries a skill reference, needs an operator's override, or runs past a screen.

Nothing under `coder/` goes inline at all. `scripts/check_prompt_agnostic.py` and
`coder/test_prompt_stack_neutrality.py` glob `coder/*/prompts/*.md`, so an inline body
would escape that workflow's central invariant.

## Map

- `src/`: the `workhorse_workflows` package, one subpackage per workflow plus the shared `kit`.
- `tests/`: the workflow tests, one directory per workflow.
