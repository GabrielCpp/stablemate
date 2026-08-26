---
name: stablemate-workhorse-prompt-writing
description: "Writing the prompt a workhorse turn dispatches — the four mechanics a section may serve (aim, inlined inputs, enforced binding rules, a rendered output contract), one prompt file per aim instead of mode variables, what never belongs in a prompt (commit protocol, skill menus, facts the cwd answers, defenses against upstream-prevented states), and the workflow-engineer audit that decides whether a section lives. Load when writing or reviewing a `prompts/*.md` under a workflow distribution, or when a prompt has grown sections nobody can tie to a check. For the node/state Python, load workhorse-engine; for general writing craft, farrier-skills-writing."
metadata:
  generated_by: farrier
  source: library/skills/workhorse/workhorse-prompt-writing/SKILL.md
  resolve: "farrier source .claude/skills/stablemate-workhorse-prompt-writing/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
  tags: [standards, docs]
---

# Workhorse workflow prompts

A prompt here is not a conversation opener — it is **one turn dispatched by a state
machine**. The flow validated the inputs before rendering it, a pydantic model parses
what comes back, and deterministic gates run after the turn. Every section of the prompt
exists to support one of those mechanics, and says which one by existing.

[[workhorse-engine]] owns the Python side of the turn (states, nodes, schemas);
[[farrier-skills-writing]] owns the general craft (leading words, no-ops, pruning). This
skill is the contract between the two: what a prompt may contain.

## The four mechanics

A section serves exactly one of these, or it goes:

1. **Aim** — one short paragraph naming the artifact this turn must leave behind: the
   thing the next node reads (a commit on the branch, a plan file, a fixed book, a JSON
   verdict). Serves the session's goal-setting. A plan pasted into the turn carries its
   own exit conditions — do not ask the agent to state its own.
2. **Inputs** — the data the flow already validated, inlined verbatim (plan text, backlog
   bullet, findings list, diff). Serves the checkpoint: the turn's context is what the
   flow recorded. Presence is the *flow's* obligation — a missing input is a workflow
   defect that loops the producing turn, so the prompt carries no `{% if %}` fallback
   arm, no "if blank, return blocked", no "go read it from disk yourself".
3. **Binding rules** — only constraints that something deterministic enforces afterwards:
   the `agents.yml` gates that run when the turn ends, a verifier that opens the files
   the result names, a parser that machine-reads a mandated shape. A rule with no check
   and no downstream reader is deleted — or, if it matters, its check is built and *then*
   the rule stays. Claims that **narrow** a deterministic check ("list the scenarios you
   proved", bound afterwards against the log) are the good pattern; self-graded promises
   ("state your success criteria, then grade yourself") are the machinery this rule
   deletes.
4. **Output contract** — rendered, never hand-written. Generate the block from the
   pydantic model itself — `model_json_schema()` over a model whose every field carries a
   `Field(description=...)` — so prompt and schema cannot disagree. Frame it as *produce
   a JSON document that complies with this schema*, never as a schema to echo back.
   Status fields the agent produces are required `Literal`s with **no default**: the
   agent is never allowed to fail its output contract, and a missing or invalid status is
   a parse failure the runner answers with a retry turn, not a blank that quietly takes a
   default arm.

Everything else goes: philosophy and motivation, another lane's responsibilities,
restatements of a rule already given, workflow trivia the agent cannot act on, and
defensive instructions for situations the flow now prevents upstream.

## One prompt per aim

A turn dispatched for two different reasons is **two prompt files**. The flow picks which
one to render — it already knows why it is dispatching. Both halves of the alternative
are banned:

- **Mode-sniffing prose** ("if the notes open with `…`, this is a string repair") makes
  the agent re-derive a fact Python holds.
- **`{% if mode %}` variables** hide two prompts inside one file, and every reader pays
  for both branches on every render.

Shared *text* between sibling prompts is fine — extract it into a partial included by
both files. Shared *dispatch* is not.

## What never belongs in a prompt

Each of these has a home that is not the prompt, and a copy in the prompt is a second
source of truth that drifts:

- **Commit protocol.** The target repo installs the `commit-and-push` policy
  (`library/policies/git/commit-and-push.md`, aggregated into its generated agent
  instructions via `localInstructions` in `agents.yml`), so every agent in that repo is
  already asked to commit finished work by explicit path with a conventional subject.
  Turn-specific trailers (`Epic:`/`Story:`) are the flow's job to apply
  deterministically, not prose to hope for.
- **Verification commands as prose.** "Never invent a verification command" dies with
  the section that needed it: the commands live in `agents.yml`, so the flow inlines
  them deterministically where a plan or turn needs them. The prompt states plainly that
  the gates run after the turn and the work must be left passing them.
- **Skill and layer menus.** A `find_by_tags(...)` listing restates what the installed
  skills already advertise through the repo's own instruction mechanism and their
  frontmatter; the model decides what to load.
- **Facts the cwd answers.** The agent runs at the repo root: it needs no
  `{{ repo.name }}`, no layer-name labels, no directory tour a `ls` replaces.
- **Machine-parsed shapes defended by prose.** If a parser reads `### Scenario N:`
  headings, the parser's gate validates the shape and loops the turn on violation; the
  prompt shows the shape once as part of the contract and stops re-warning about it.

## The audit

Prompts stay **free-form** — no imposed skeleton, no section order. The discipline is an
audit, not a template: for every section, justify it *as a workflow engineer* — name the
mechanic it supports and why the flow needs it there.

- No mechanic named → the section is deleted.
- The justification names a check that does not exist → build the check or lose the rule.
- Two sections serve the same mechanic → one is a restatement; deletion, not a merge.
- A rule stated more than once → keep the copy nearest its enforcement, delete the rest.

Run the audit whenever a prompt is touched, over the whole file — sediment settles
section by section, and the audit is the only force pointing the other way.
