---
name: stablemate-root-cause
description: "Judging whether a fix reaches the origin of a defect or handles its symptom, with no knowledge of the domain: the causal chain written before the edit (symptom, mechanism, origin stated as a decision, prediction), the shape tests that reject a story on its form (fix downstream of where the value first went wrong, a branch added for the case, a classifier reading fewer inputs than its distinction needs, two components disagreeing in writing, an explanation covering exactly one failure, a loop converging only with an exception list), the unfixable-versus-unclassifiable question, and what an escape hatch carries when taken. Load when about to add or extend a waiver, retry, sleep, default, fallback, skip, broader except, null check or IOU, when a loop converges only with an exception list, when reviewing a diff that clears a failure, or when reporting a phase complete with a workaround inside it. For finding the defect itself, load diagnosing-bugs."
metadata:
  generated_by: farrier
  source: library/skills/root-cause/SKILL.md
  resolve: "farrier source .claude/skills/stablemate-root-cause/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
  tags: [standards, review]
---

# Root cause or symptom

[[diagnosing-bugs]] finds the defect. This skill judges the *fix* — and it fires on an
action, not a topic: the moment you reach for a branch that **handles** a case rather than
removes it. A waiver, a retry, a sleep, a default, a fallback, a skip, a broader `except`, a
null check, an IOU, a better place to file the exception. Each is a **hatch**: a way for the
work to converge without the case going away.

A hatch is sometimes right. What decides is not the domain — you may not know it — but the
**shape** of the story behind the hatch. A sound causal story has a fixed form, and an unsound
one fails that form before anyone has to judge whether it is true. That is why this skill
carries no evidence of its own: it tells you what a cause *looks like*, and lets you check
your own reasoning against it with nothing but the reasoning in hand.

## The chain

Write these four lines **before the edit**, in the report or the plan, in this order. The
shape of each line is the test; content comes after.

1. **Symptom** — what was observed. Error text is allowed here and nowhere else.
2. **Mechanism** — how the wrong value or state was produced. One sentence, containing no
   error text. A mechanism restated in the error's own words is the symptom again.
3. **Origin** — the *decision* the mechanism came from: a line that chose, a check that
   classifies, a design that assumed. An origin is a verb with a subject. "The names collide"
   is a noun and stops short; "the doctor decides the layer from the code alone" is a decision
   and arrives.
4. **Prediction** — one other thing this origin causes today, or one thing the fix makes pass
   without touching it. A cause explains more than the failure it was found through; a story
   that explains exactly the one symptom and nothing else is a description wearing a cause's
   clothes.

A chain that ends at a noun, contains error text past line 1, or has no prediction is sent
back on its form. Nobody needs to know the domain to send it back.

## Shape tests

Flat reference. Ask each of your own story; a *yes* means it is not yet a cause. They are
answerable with zero knowledge of what the code does.

- **Downstream.** Does the fix sit where the wrong value was *consumed* rather than where it
  was *produced*? A consumer-side change — a guard, a default, a wait, a catch, a waiver — is
  a symptom fix until the chain shows the producer is out of reach.
- **A branch for the case.** Does the diff add a path that takes the bad case somewhere, rather
  than removing the case? A branch is a decision to live with it. Sometimes that is the
  decision; it is never the fix.
- **Fewer inputs than the distinction.** Does something decide between A and B while reading
  only what A and B have in common? Ask what you would have to *see* to tell them apart, then
  ask whether the decider reads it. A classifier fed one of the two layers it classifies
  cannot be right, and everything downstream that papers over its output is evidence of
  that, not a feature.
- **Disagreement in writing.** Do two components describe the same signal differently — a
  docstring calls it a doc defect, a consumer treats it as a code defect? That is a
  classification gap, and neither side knows it exists. The gap is the origin.
- **Exactly one failure.** Does your explanation cover the one failure you saw and predict
  nothing else? See line 4 of the chain.
- **Convergence by exception.** Does the loop terminate only because a list of cases is
  excluded from it? Then the list is the finding, and it grows on every run.
- **Handling, routing, reporting.** Is the work improving where the case's paperwork goes —
  a tidier waiver, a better-placed IOU, a clearer log — rather than the number of cases?
  Improving the apology is the most comfortable form of the symptom fix, because the change
  is real and worth having, and the phase feels done.
- **"Cannot be fixed here."** Does the claim come without naming *where* it can be fixed, and
  whether the evidence to fix it already exists somewhere in the repo? Unreachable is a
  location, not a feeling.

## Unfixable or unclassifiable

The question that separates a hatch that is right from one that is bought: **is this case
genuinely unfixable, or merely unclassifiable?**

A pipeline that needs a hatch to converge is usually not facing a stubborn defect. It is
facing a classification it cannot make — two different situations emitting a byte-identical
finding, because the decider reads one layer and the difference lives in the other. The hatch
then pays for a distinction nobody drew. The evidence that would draw it often already exists
in the repo, unread by that decider: a rendered tree the check never consults, a trace the
gate never opens, a second source the classifier never joins.

Only an unfixable case justifies a hatch. An unclassifiable one justifies reading the other
layer.

## Taking the hatch anyway

Sometimes the origin is real, out of reach, and the work must converge now. A hatch taken
that way is a **debt**, and it carries its chain with it: the four lines above, plus the
origin it is *not* fixing and why that origin is out of reach from here. Write that beside
the hatch — in the waiver entry, the skip reason, the IOU text, the report — so the next
reader finds the cause where they find the workaround.

Having to write the origin down is what most often turns the hatch back into a fix. That is
the point, and it is why the writing comes before the edit rather than after.

A hatch also needs its **exit**: what removes it, and what checks that it was removed. A
waiver nobody deletes pre-waives the next genuine occurrence at the same spot; a skip nobody
revisits is a test that used to exist. Name the condition under which the hatch goes, and the
gate that will notice when it has.

## Completion criterion

The work is done when every line below is true, and each is checkable from the diff and the
report alone:

- The chain is in the report, all four lines, in shape.
- Every hatch the diff adds or extends carries its chain and its exit beside it.
- The prediction was run — the other consequence was observed, or the untouched thing now
  passes — and the result is in the report.
- A phase reported complete names every hatch still standing inside it, or says there are
  none.

A phase with a hatch in it and no chain is not complete. It is a phase that improved the
routing of an apology.

## Reviewing someone else's fix

The same tests, applied to a diff you did not write. Read the failure it clears, then ask of
the diff: producer or consumer; branch or removal; one failure explained or more. A diff that
touches a waiver file, a skip marker, a retry count or a broader `except` with no chain in the
description is the review finding, whatever the tests say afterwards. [[code-review]] carries
the rest of the review; this is the part that decides whether the fix is one.
