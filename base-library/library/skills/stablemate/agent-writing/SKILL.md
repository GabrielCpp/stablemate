---
name: agent-writing
description: "How to write a document an agent reads — a skill, a prompt, a CLAUDE.md, a doc reached by a link: the context pointer and how its wording decides whether the material is ever reached, the two loads a document spends, the information hierarchy and the progressive-disclosure move down it (SKILL.md + references/), completion criteria that resist premature completion, leading words, why prohibition backfires, and the pruning tests that keep a document relevant. Load when writing or editing a skill, a prompt, or an instruction file, when a document has sprawled past the point an agent attends to all of it, or when an agent keeps missing material that is already written down. For which surface material belongs on, load repo-docs; for the library's plumbing, agent-library."
tags: [standards, docs]
---

# Writing for agents

This skill is about the **writing** — the levers that make an agent take the same process
every run. Its neighbours own the other two halves: [[repo-docs]] decides *which surface*
material belongs on (root `CLAUDE.md`, nested, README, `docs/`), and [[agent-library]] owns
the plumbing (library layout, `agents.yml` selection, `make agent-install`). The packaging
differs across all three; the writing does not.

When the document is a **skill**, also read
[references/skill-mechanics.md](references/skill-mechanics.md) — frontmatter, the
skill-versus-prompt choice, and how a skill discloses material into `references/`.

The target is not a document that produces the same *output* every run. It is one that makes
the agent take the same *process*.

## Context pointers

A **context pointer** is a reference held in the agent's context that names material sitting
outside it and encodes the condition for reaching it. A skill's `description` is one. So is a
line in `CLAUDE.md` naming a doc, and a link in a skill body to a `references/` file.

The pointer's **wording**, not its target, decides whether the material is reached — and how
reliably. A must-have target behind a weakly worded pointer is a variance bug: the material
is written, correct, and read on some runs and not others. Sharpen the wording first; inline
the material only if sharpening fails.

A pointer does two jobs — say what the material is, and list the **branches** that should
trigger reaching it. A branch is a distinct case the document handles, so different runs take
different paths through it. An always-loaded pointer spends tokens on every turn whether or
not it fires, so it earns harder pruning than the body:

- **Front-load the leading word.** The pointer is where it does its triggering work.
- **One trigger per branch.** Synonyms renaming a single branch are one branch written twice.
  Collapse them; keep only genuinely distinct branches.
- **Cut identity the body already carries.**

The `description` on every skill in this library is written to this bar. Read a few before
writing a new one — they name the branches explicitly and end on a "Load when…" clause.

## The two loads

Every document and every pointer spends one of two budgets:

| Load | Paid by | Spent on |
| --- | --- | --- |
| **Context load** | the agent's window | always-loaded material — a `CLAUDE.md` line, a skill `description` — costing tokens and attention every turn, fired or not |
| **Cognitive load** | the human | knowing which documents exist and when to reach for each |

Material behind a pointer escapes context load at the price of the pointer's own line.
Material with no pointer at all rides entirely on cognitive load — the human is its index.

Cognitive load is not a cost to minimise. It is the price of human agency: spend it where
human judgement matters, remove it where it does not.

## The information hierarchy

A document is built from two content types that mix freely — **steps** (ordered actions the
agent performs) and **reference** (definitions, rules, facts consulted on demand). A document
can be all steps (a procedure), all reference (this skill), or both.

The decision is where each piece sits on the hierarchy, ranked by how immediately the agent
needs it:

1. **In-file step** — the primary tier: what the agent does, in order.
2. **In-file reference** — consulted on demand. Often a legitimately flat peer set (every
   rule of a review on one rung). That is a fine arrangement, not a smell.
3. **Disclosed reference** — pushed into a separate file behind a pointer, loaded only when
   the pointer fires. Spans a sibling `references/*.md` through fully external material any
   document can link.

Push too little down and the top bloats; push too much and you hide material the agent
actually needs. That tension is the whole decision.

**Progressive disclosure** is the move down the ladder. It is not primarily a token
optimisation — it is how the hierarchy is protected. **Branching is the cleanest test:**
inline what every branch needs, disclose what only some branches reach. In a document with
steps, in-file reference that should have been disclosed buries them, and attending to them
becomes a coin flip.

**Sprawl** is the failure mode here: a document simply too long, even when every line is live
and unique. Attention thins across the excess, and every extra line is one more to keep
relevant. The cure is the ladder — disclose reference behind pointers, and split by branch or
sequence so each path carries only what it needs. `make check-skills` fails a `SKILL.md` past
its line budget with nothing disclosed, because sprawl is the one failure here that a machine
can see.

**Co-location** is the within-file companion. Where the ladder decides *how far down* a piece
sits, co-location decides *what sits beside it* once there: keep a concept's definition,
rules and caveats under one heading rather than scattered, so reading one part brings its
neighbours. (Distinct from duplication — that repeats one meaning in two places; scattering
fragments one meaning across many.)

## Steps and completion criteria

Every step ends on a **completion criterion** — the condition telling the agent the work is
done. Two properties make it a lever:

**Clarity** — can the agent tell done from not-done? A vague bound ("understanding reached")
invites **premature completion**: ending the step before it is genuinely done, attention
slipping to *being done*. The visible steps still ahead supply the pull; the criterion's
clarity is the resistance. Defend in order — sharpen the bound first, since it is local and
cheap. Only if it is irreducibly fuzzy *and* you observe the rush, hide the later steps by
splitting the sequence. Hiding works only across a real context boundary (a hand-off, a
subagent dispatch); an inline call leaves the later steps in context and clears nothing.

**Demand** — how much it requires. "Every modified model accounted for" forces thorough work
where "produce a change list" does not. Demand drives the digging the agent does *within* the
work, latent in the wording rather than written as its own step. It is not step-bound: "every
rule applied" binds a body of flat reference exactly as "every step done" binds a sequence,
which is how an all-reference document still carries an exhaustiveness bar.

The strongest criteria are both checkable and exhaustive. Prefer one naming a command whose
exit status settles it — `make lint` passes, `ostler doctor` is clean — over one naming a
state of mind.

## Leading words

A **leading word** is a compact concept already living in the model's pretraining that the
agent thinks with while running the document — *seam*, *tight*, *red*, *tracer bullet*,
*fog of war*. Repeated as a token, never as a sentence, it accumulates a distributed
definition and anchors a whole region of behaviour in the fewest tokens, by recruiting priors
the model already holds.

It anchors twice. In the body, **execution**: the agent reaches for the same behaviour every
time the word appears, and inside flat reference it focuses attention on a class of thing to
look for. In a pointer, **invocation**: when the same word lives in your prompts, your docs
and your code, the agent links that shared language to the material and reaches it more
reliably. This is why the library's vocabulary is worth keeping consistent — *seam*, *node*,
*obligation*, *gate*, *surface* mean one thing across every skill here.

Coining your own works if you define it clearly, but a made-up word recruits no priors: you
pay in definition tokens what a pretrained word gives free. Reach for an existing word first.

Hunt for passages begging to collapse into a single token — a triad spelled out at three
sites, a pointer spending a sentence to gesture at one idea:

- "fast, deterministic, low-overhead" → *tight* (a *tight* loop).
- "a loop you believe in" → *red* — a fuzzy gate becomes a binary observable state.

**Negation** is the failure mode beside this lever. Steering by prohibition drags the
forbidden behaviour into context and makes it *more* available, not less: the negation is a
weak modifier that the strongly-activated concept overruns, so the ban half-reads as an
instruction. Prompt the **positive** — state the target behaviour so the banned one is never
spoken. A prohibition earns its place only as a hard guardrail you cannot phrase positively
(this repo has a few: no environment in a workflow, no private name in the tree), and even
then pair it with the positive target.

## Pruning

- **Single source of truth.** One authoritative place per meaning, so changing the behaviour
  is a one-place edit. Duplication costs maintenance and tokens, and inflates a meaning's
  prominence past its real rank. (The accidental inverse of a leading word, which repeats a
  token on purpose, never the meaning.)
- **The environment is a source of truth too** — `Makefile` targets, `pyproject.toml`, the
  directory layout, `--help` output. A document restating it is a **cache**, earning its load
  only when the lookup is expensive. Cache what the agent cannot find by looking: the
  unwritten convention, the reason behind a choice, the gotcha no config confesses. Leave the
  one-command lookups to the environment, where they cannot go stale.
- **Relevance.** Does the line still bear on what the document does? A line loses relevance by
  never bearing on the task (exposition, or a branch that should be disclosed) or by going
  stale as the world it describes changes. Without a pruning discipline the default fate is
  **sediment**: stale layers that settle because adding feels safe and removing feels risky.
- **No-ops.** An instruction the model already obeys by default pays load to say nothing. The
  test — does it change behaviour versus the default? — is *model*-relative, not
  reader-relative: two people disagreeing about a no-op disagree about the default, and
  settle it by running the document, not by debate. When a sentence fails, delete the whole
  sentence rather than trim words from it. The test also grades leading words: a word too
  weak to beat the default (*be thorough*, when the agent is already thorough-ish) is a
  no-op, and the fix is a stronger word, not a different technique.

## Verification before calling the work done

```bash
make check-skills        # sprawl budget, disclosure reachable, no skill driving a prompt
make check-library       # the frontmatter fence still parses (a broken one loses tags silently)
```

**[scripts/check_skills.py](scripts/check_skills.py)** is what the first one runs, and it
installs here so it travels with the doctrine — a repo that takes this skill takes the guard
that makes it hold.

Then read it top to bottom once and ask of every line: does this change behaviour versus the
default? Anything that fails goes to its rung on the hierarchy, or goes away.

## When to reach for the neighbors

- **Which surface the material belongs on** — root vs nested `CLAUDE.md`, README, `docs/` →
  [[repo-docs]]. That skill decides *where*; this one decides *how it is written*.
- **Library plumbing** — adding a skill to a pack, `agents.yml` selection, re-installing the
  generated `.claude/` and `.github/` copies → [[agent-library]]. Those copies carry a
  `do_not_edit` key: change the library source and re-install.
- **The document is a skill** → [references/skill-mechanics.md](references/skill-mechanics.md).

---

*The doctrine here is adapted from [`mattpocock/skills`](https://github.com/mattpocock/skills)
(`writing-for-agents`), MIT-licensed, retargeted at this library's mechanics.*
