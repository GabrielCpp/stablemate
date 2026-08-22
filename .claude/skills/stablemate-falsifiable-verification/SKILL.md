---
name: stablemate-falsifiable-verification
description: "The bar a `verify:` bullet has to clear before it counts as an observation: name the state of the world in which the check goes red, assert the before-state rather than assuming it, and discriminate the claim from its nearest plausible defect. Load when writing or backfilling `verify:` bullets on an OKF node, when repairing an `undeclared-obligation`, `weak-check` or `unstated-precondition` finding, or when reviewing checks somebody else declared."
metadata:
  generated_by: farrier
  source: library/skills/stablemate/falsifiable-verification/SKILL.md
  resolve: "farrier source .claude/skills/stablemate-falsifiable-verification/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
  tags: [standards, docs, qa]
---

# What makes a verification falsifiable

A `verify:` bullet is not a promise that the behaviour works. It is the **observation that would
show it does not**, written down before anyone goes looking. So there is one question to ask of
every check, and everything below is a way of answering it:

> **Name the state of the world in which this check goes red.**

If the answer is "the whole feature is missing" or "the process did not start", the check is a
rubber stamp: it will be green the day the defect ships. A check earns its bullet by ruling out a
defect that is *plausible for this claim* — the near miss, not the catastrophe.

For the vocabulary itself — the calls, their arguments, where the bullet goes — see
[[ostler]] → "The OKF UI profile". For declaring checks while modelling a service in bulk, see
[[okf-modeling]]. This skill is only about whether what you declared could ever fail.

---

## The three preconditions

A check that meets the bar satisfies all three. They are preconditions, not a rubric: miss one and
the observation is not an observation.

### 1. The subject is named concretely

`unchanged(subject="the object")` names nothing a scenario can read twice. `unchanged(subject="the
manifest", except_fields=["pages.getting-started.fr.slug"])` names a document and the one field
licensed to move. The subject is what the harness resolves and what a failure message quotes — if
two different things could satisfy it, a red run cannot say which one moved.

### 2. The before-state is asserted, not assumed

This is the precondition most often skipped, and it is the one that silently converts a claim into
a tautology. A creation observed only *after* the action passes identically when the subject was
already there, so a no-op and a success are the same observation:

```markdown
# unfalsifiable — 201 and a present id say the same thing either way
- does: creates a revision under the caller's name
- verify: http_status(201, path="/revisions")
- verify: json_path(path="$.revision.id", absent=false)
```

```markdown
# falsifiable — the absence before is part of what is observed
- does: creates a revision under the caller's name
- verify: created(subject="the caller's revision")
- verify: json_path(path="$.revision.author", equals="the caller")
```

`created` and `removed` exist for exactly this: the harness insists on a `(before, after)` pair and
refuses an after-only read at the call. The mirror case is a delete asserted by absence afterwards
— which passes on a subject that was never there, so `removed(subject=…)` is what makes the
disappearance attributable to the action rather than to history.

The rule generalises past existence. Any claim of the form *X changed* needs the read before it:
that is what `unchanged`, `keys_unchanged`, `persists` and `conflict_on_stale` are, and it is why
none of them can be spelled as a single after-read.

### 3. The check discriminates the claim from its nearest plausible defect

Ask what the *likely* bug is, not the worst one, and choose the check that separates them.

| The claim | The near-miss defect | The check that tells them apart |
| --- | --- | --- |
| the field is returned | it is returned empty, or as the default | `json_path(path=…, equals=…)`, never presence alone |
| the request is refused | it is refused for a different reason | `http_status(code=409, title="Stale Hold")` |
| the write survives | it was only observed through the session that made it | `persists(subject=…)` |
| one record moved | it was copied and the old one left behind | `keys_unchanged(subject=…)` |
| the update is conditional | it is an unconditional overwrite | `conflict_on_stale(subject=…, token=…)` |
| the effect fired | it fired at the source, or fired twice | `emitted(event=…, count=…)` |
| one row was deleted | the neighbours were rewritten too | `unchanged(subject=…, except_fields=[…])` |
| the refusal says nothing it may not | it quotes the credential, path or query it rejected | `omits(subject=…, matches=…)` |

Every check in the vocabulary carries the defect it excludes in its own spec — `ostler checks`
prints them. If you cannot say which line of that table your check is on, you have not chosen a
check yet.

---

## One check per obligation

Obligations are minted per normative bullet, and a check is bound to what it observes — **document
order is the binding**, not a convention. Each `verify:` belongs to the nearest normative bullet
above it, and one written before any of them belongs to the node's own contract. So a node with six
`does:` bullets and one `verify:` has declared one observation and left five claims unprovable, and
`undeclared-obligation` will not fire, because the node declared *something*: the per-claim gap is
`qa validate`'s `claimed-but-unasserted`, raised against the plan that has to prove it.

Write each check under the bullet it observes. A check written above the claim attaches to whatever
precedes it, which is how a refusal's status ends up filed as the observation of the success case.

The reverse move is worse and is forbidden: **never collapse bullets to make one check cover
them.** That deletes obligations to make a count come out even.

The same rule bans the other shortcut — **never delete or weaken a claim to clear a finding.** A
node whose finding count fell because its `does:` bullets got vaguer has been made green by
removing the thing under test.

---

## What `doctor` can see, and what it cannot

Three findings exist for the three ways a node ends up unprovable, and all three are waivable per
finding through the waivers file when the book knows better than the rule. Two are `warn`, because
the remedy is authoring judgment. `weak-check` is an `error`: a claim whose every check passes on
the defect it names is not a judgment call, and it is raised per claim — a discriminating check
written under one bullet no longer answers for its siblings.

| Code | What it caught | What to write instead |
| --- | --- | --- |
| `undeclared-obligation` | the node mints obligations and declares no check at all | a check per observation |
| `weak-check` | every check declared *for that claim* passes on the defect it names — a field asserted present with no value, a `2xx` naming neither `path:` nor `title:` | name the value, the route, or the title the claim turns on |
| `unstated-precondition` | a bullet says the node creates or removes something and the checks read only the state afterwards | `created(subject=…)` / `removed(subject=…)` |

What no linter can see is precondition **3**: whether the value you asserted is the one the defect
would get wrong. `json_path(path="$.state", equals="published")` is discriminating for a state
machine and a rubber stamp on a field that is hard-coded to `"published"`. That judgment is the
author's, and it is the reason these are warns and this skill exists.

---

## Reviewing somebody else's checks

Read the `does:` bullet, invent the most likely wrong implementation, and run it against the
declared checks in your head. If it comes out green, the check is the finding — not the code.

Two shapes that fail this every time:

- **The check that proves the endpoint exists.** `http_status(code=200)` with no `path:` and no
  `title:` says a request succeeded and nothing about which request or what it answered.
- **The check that repeats the request.** Asserting the value the caller just sent back, rather
  than what the system did with it, is a round-trip test of the serialiser.
