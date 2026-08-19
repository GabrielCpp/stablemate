---
name: stablemate-repo
description: "The stablemate monorepo's own always-loaded rules: what the workspace contains, that the repo ships publicly and no private overlay name may appear in it, that a workflow reads no environment, that ruff and ty must both be clean, and which Conventional Commit scopes the hook accepts. Aggregated into the repo root AGENTS.md; load it directly only when working on stablemate from outside that root."
applyTo: ""
tags: [standards, stablemate]
---

# stablemate

A `uv` workspace monorepo of the agent-workflow tooling: **workhorse** (the runner
driving an agent CLI through a checkpointed Python state machine), **workflows**
(those state machines), **farrier** (the installer), **ostler** (the doc-graph
validator), plus `core`, `groom`, `saddlebag`, `base-library` and `benchmarks`.
Python ≥ 3.12. Every subproject has a README — read it before changing that
component. Only `workhorse/` also has a nested `CLAUDE.md`; the other eight are
README-only, so don't hunt for per-package instruction files that aren't there.

A workflow is **Python**, not YAML. The YAML engine is retired — no `workflow.yml`,
no `requires:` block, no node-graph document. Prose describing one is stale; fix it.

## stablemate is public (load-bearing)

This repo ships publicly. No private overlay project's name may appear in it — not in
prose, not in a fixture, not in a code comment. Examples use neutral placeholders:

| Placeholder                          | Stands for                          |
| ------------------------------------ | ----------------------------------- |
| `acme`, `globex`                     | a client repo / brand               |
| `api-service`, `web-app`, `mobile-app` | repos in a multi-repo workspace    |
| `example.com`, `example-org`         | hostnames, GitHub orgs              |

The banned names are deliberately **not written down anywhere in the tree** — a denylist
publishes the words it bans, and so does a hash of one. `scripts/private_names.py` reads
them from an untracked source instead: `$STABLEMATE_PRIVATE_NAMES`, or
`$GIT_DIR/private-names` (one per line; `.git/` is never committed).

```bash
make install  # once per clone: venv + hooks (`make hooks` for the hooks alone)
```

The hook blocks any commit whose staged paths or added lines carry a configured name.
With no list configured (a public contributor) it is a no-op.

The same resolver backs `scripts/check_public.py` — the whole-tree sweep the hook cannot
be, since the hook only ever sees staged changes. It scans every **tracked** file (path
and content), walks the **reachable git history** (`--history` runs that half alone —
a name committed and later removed still ships in every clone, and only a rewrite fixes
it), and also asserts the base library stands alone, i.e. that no base skill or
workflow depends on the private overlay. Both failure modes are invisible on a machine
where the overlay is configured and shadows everything, which is why they need a check
rather than attention.

```bash
make check-public    # also runs as part of `make test`
```

## A workflow reads no environment (load-bearing)

`os.environ` / `os.getenv` are **prohibited** anywhere under
`workflows/src/workhorse_workflows/`. Everything a node or a state needs is an argument
or a workflow parameter — a field on the `Workflow` subclass, settable with `--param`.
A value read from the environment is in no checkpoint (so a resume silently takes a
different one) and in no telemetry, and `--params` cannot set it.

The process boundary is where the environment belongs, and it is outside that package:
`workhorse/cli/run.py` and `workhorse/supervisor.py` translate `$FOO` into `--params`
once, on the way in. The one allowlisted module is `kit/credentials.py`, and for the
opposite reason — a secret must *never* become a checkpointed `--param`.

```bash
make check-no-env    # also runs as part of `make test`
```

The full rule, including `Workflow.injects` for the ambient paths
(`repo_dir`/`docs_path`/`workspace_file`), is in
[workflows/README.md](workflows/README.md).

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

The auto-resolver a block routes through (`prompts/resolve-operator.md`) **applies
decisions; it does not make them.** It may write `STATUS: ANSWERED` and let the loop
continue only when it can quote the thing that already settles the question — a record
under `<docs-root>/decisions/`, a convention in `AGENTS.md` or an installed skill, an
acceptance criterion in the story's own spec — and it publishes that citation in the
answer and in the run log. A question with a written answer costs a human nothing to be
asked and teaches them nothing when they answer it the way the document already says.

A question *without* one is theirs by definition, and the resolver escalates: an unwritten
product or scope call, two sources that genuinely conflict, anything needing a credential
or a spend, and every block where the resolver is the interested party (it never narrows
its own QA `covers:`, stamps its own status, or edits its own evidence). "I am not sure" is
an escalation too. The parking half of this rule is untouched — a block it cannot ground
`Await`s, as many times as it takes, and never ends the run.

The place decisions accumulate is `<docs-root>/decisions/`
(`coder/shared/paths.py::decisions_dir`), and answering writes one, so the second run to
hit the same question reads the ruling instead of parking on it again. Every lane caps the
*resolver* rather than the block — `MAX_PLAN_BLOCKS`, `MAX_REVIEW_BLOCKS`, `MAX_QA_BLOCKS`
— and spends that budget on an answer exactly as on an escalation, so a resolver that keeps
applying a rule the block does not clear walks toward a person instead of lapping forever.
The branch, the vocabulary and the argument all live in `coder/shared/resolution.py`.

```bash
make check-no-giveup    # also runs as part of `make test`
```

This guard is narrow: it stops the specific vocabulary of a deleted give-up pattern from
quietly reappearing, not every way the rule could be broken. It does not cover the
resolver-authority half of the rule — that an `answered` arm exists only where the answer
was grounded in something already written, at the `operator_mode` sites in
`author/workflow.py`, `author/surveyor/flow.py`, `coder/dev/flow.py`,
`coder/review/flow.py`, `coder/qa/flow.py` and `coder/docs/flow.py` — which needs the
control-flow graph, not a grep, same as everything else this check cannot see
structurally. See the script's own docstring before widening it.

## Python linting (load-bearing)

This repo is linted with **ruff** *and* type-checked with **ty**. Keep both clean — zero
findings is the bar, and a change isn't done until `make lint` passes.

```bash
make lint               # both, from the repo root — every subproject in one pass
ruff check . --fix      # apply the autofixable ones (unused imports, etc.)
```

`make test` runs `make lint` first, so a type error fails the suite rather than waiting
for a reviewer.

- Run it from the **repo root** before wrapping up any Python change, so all of
  workhorse/farrier/ostler are covered in one pass.
- Fix the finding, don't silence it: prefer correcting the code over adding
  `# noqa` / `# ty: ignore` or broadening ignores. Reach for config/ignores only when a
  rule is genuinely wrong for this codebase, and say why.
- The same bar applies to test files — unused imports, ambiguous names (`l`/`I`/`O`),
  multi-statement semicolon lines, and a fake that has drifted from the port it stands
  in for are findings, not style preferences.
- `# type: ignore[...]` is mypy's spelling and is **inert** for ty. The one that
  suppresses is `# ty: ignore[rule]`, and it names the rule.
- Config for both lives in the root `pyproject.toml` (`[tool.ruff]`, `[tool.ty]`); keep
  it there so every subproject shares one ruleset. ty runs with every rule at its default
  severity and no ignore list — the only exception is a path in `[tool.ty.src] exclude`.

The full rationale, and the fixes that recur, are in the `python-cli`, `python-testing`
and `python-architecture` skills.

## The commit scopes this repo accepts

The cadence, the message format and what each type releases are below, in the commit
procedure this file aggregates. What is specific to stablemate is the scope vocabulary:
one tracked top-level directory — `core`, `workhorse`, `workflows`, `farrier`, `ostler`,
`groom`, `saddlebag`, `base-library`, `benchmarks`, `docs`, `scripts` — or one of
`deps`, `release`, `ci`, `lint`, `hooks`. Omit the parentheses entirely for a repo-wide
change.

```bash
make install  # runs `pre-commit install`, which wires up all three commit guards
```

`.githooks/commit-msg` derives those scopes from the tracked top-level directories, so a
new workspace member needs no edit. `git commit --no-verify` bypasses it. A generated
message — Zed's *Generate commit message*, an agent's — only ever biases toward this
format; the hook is what makes it hold.

The gate before a stablemate commit is `make lint` from the root, plus the affected test
package.
