# Documentation review defect kinds

The eight `kind` values a documentation review may return
(`workflows/src/workhorse_workflows/coder/shared/schemas/docs.py`). A review finding is a
repair contract: it names a file and anchor, classifies the defect with one of these labels,
and states the smallest acceptable repair. This file is what each label means, and — where one
exists — the `ostler doctor` code that is its mechanical half. Companion to
[`../SKILL.md`](../SKILL.md); see [doctor-codes.md](doctor-codes.md) for the codes and
[bullet-grammar.md](bullet-grammar.md) for the grammar the last four turn on.

Both sides of the loop read this file. A reviewer that classifies against it files findings an
author can act on without re-deriving the standard; an author who has read it writes fewer of
them. A defect that fits none of these labels is not a documentation defect — say so in the
notes rather than stretching a label to hold it.

## `node-type`

The content is documented, under the wrong type. A browser click under `## Invocations`, a CLI
subcommand under `## Interactions`, an HTTP handler as a `method`. The type decides which
bullet keys exist, which of them mint obligations, and which container heading the node lives
under, so the wrong type silently drops the claims the right one would have graded.

Repair: move the node under the right heading and re-key its bullets. The per-type references
in [node-types/](node-types/) settle which type applies, and each one opens with when to reach
for it rather than its neighbours.

Doctor half: partial. `bad-heading-type` and `unknown-type` catch a *misspelled* heading;
nothing catches a well-formed node of the wrong kind, which is why this is a review label.

## `missing-node`

The implementation delta added a surface, endpoint, command, method, field or flow step that
the book does not have. The book is the as-built record of what the story shipped, so an
undocumented unit is a false book — not an incomplete one.

Repair: `ostler scaffold` the node, then author its required bullets. Judge against the diff,
not against the story text: a helper the story never mentioned but the change added is in
scope; a unit the change did not touch is not.

Doctor half: none. Doctor validates what is written, and cannot know what was not.

## `flow-coverage`

A `flow` node does not cover the path the story shipped: a `steps:` chain that stops short of
the outcome, a branch with no documented end, an interaction the flow walks through that no
longer exists. `start:` and `end:` are normative on `flow`, so an incomplete chain mints an
obligation the QA plan cannot satisfy.

Repair: extend or correct the `steps:` chain and restate `end:` as the observable outcome.
`ostler graph` is the structural authority for what reaches what.

Doctor half: `unreachable-screen` and `unresolved-relation` catch the broken links; the
*incompleteness* of a chain that resolves is a judgement.

## `overclaim`

A claim the cited evidence does not support. The classic shape: the `code:` grounding and the
cited test exercise a mouse click, and the bullet claims keyboard reordering too. Also: a
bullet that generalizes past the one case the implementation handles, or asserts a guarantee
(ordering, atomicity, retry) the code does not make.

Repair: narrow the bullet to what the cited code and test actually establish, or ground the
wider claim properly. Prefer narrowing — the book records what was built.

Doctor half: none. Doctor reads the graph, not the code's semantics.

## `grounding`

The `code:` citation is wrong, missing, or no longer points at the symbol that owns the
behaviour. A re-export does not ground a citation: the file named must *declare* the symbol.

Repair: read the file, find the symbol that owns the behaviour now, repoint the bullet. Never
restore a deleted symbol's name to satisfy a check, and never waive it — a dangling citation
means the bullet is describing code that no longer exists, which is a content defect wearing a
link defect's clothes.

Doctor half: `dangling-code-ref` (file missing) and `missing-code-symbol` (symbol not declared
there), both errors. If doctor is already red on the node, the finding is redundant — say so
and let the gate carry it.

## `bullet-granularity`

One normative bullet states more than one provable claim. One bullet is one obligation proved
by one scenario, so a fused bullet is covered by whichever half the QA planner happened to
read, and the other half ships unproved.

Repair is **repeating the key**, not rewording:

```markdown
- does: rejects a slug already in use with 409
- does: rejects a slug longer than 64 characters with 422
```

Doctor half: `compound-normative-bullet` (warn) for more than one observation in a bullet,
`overlong-normative-bullet` (error) past 700 characters of prose. The warn is a heuristic and
under-fires; a bullet joining two claims with a comma often passes it.

**Splitting a bullet does not by itself require a new check per fragment.** A `verify:` above
a group of normative bullets binds to the node's contract and covers all of them; a `verify:`
below one binds to that one. So a split under an existing contract-level check leaves the
fragments checked. What a split *does* require is that each fragment still be discriminated —
if one check could only ever go red on one of the two claims, the other fragment now needs its
own. State which case you are in; a finding that says "split, therefore add checks" is wrong
as often as it is right, and it is what makes the loop cycle.

## `verify-overclaim`

A declared check that cannot go red on the defect its claim forbids. The check is present, it
parses, it passes — and it would pass just as happily against the broken implementation. That
is worse than no check, because the obligation reads as proved.

The bar, from [`falsifiable-verification`](../../falsifiable-verification/SKILL.md):

1. **Name the subject concretely.** `count(subject="rows", equals=1)` proves nothing about
   which rows; `count(subject="links for user alice", equals=1)` can go red.
2. **Assert the before-state rather than assuming it.** A check that reads only the state
   afterwards passes on the no-op where the subject was already there. Declare a lifecycle
   change as a change: `created(subject=…)` / `removed(subject=…)`.
3. **Discriminate from the nearest plausible defect.** Write down the state of the world in
   which this check goes red. If that state is one no realistic bug produces, the check is
   decorative.

Repair: replace or add a check that goes red on the named defect.
[check-vocabulary.md](check-vocabulary.md) carries all 14 checks with, for each, the defect it
excludes — pick the one whose `excludes` names the defect this claim forbids.

Doctor half: `weak-check` (error, raised per *claim*) and `unstated-precondition` (warn, the
lifecycle case). `undeclared-obligation` (warn) is the degenerate version: a node that mints
obligations and declares no check at all.

## `author-decision`

Convergence needs a decision the reviewer cannot make and the story does not settle: two
plausible models of the same behaviour, a name only the product owner can choose, a scope
question about whether an adjacent unit is in this story's delta.

Repair: none the author can apply alone. This is the label that carries a `blocked` verdict —
state the decision needed and both options. Do not use it to avoid picking a verdict on a
defect that *is* judgeable; `revise` exists to carry an unwelcome one.

A frequent false positive: the **multi-repo `semantic` exemption**. Grounding a bullet in a
symbol that lives in a repo this story did not check out is expected, not a defect, and the
author is explicitly excused from it. Do not file it under this label or under `grounding`.
