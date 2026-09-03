---
name: stablemate-root-cause
description: "Judging whether a fix reaches the origin of a defect or handles its symptom, with no knowledge of the domain: the why-chain written per proposed fix before the edit (why is the fix needed, what caused that, how could it have been prevented, and again on the prevention until the answer is a core property of the problem), the stop test for a core property, the shape tests that reject a story on its form (fix downstream of the producer, a branch added for the case, a classifier reading fewer inputs than its distinction, two components disagreeing in writing, a loop converging only by exception list), the unfixable-versus-unclassifiable question, and what a hatch carries when taken. Load when about to add or extend a waiver, retry, sleep, default, fallback, skip, broader except, null check or IOU, when a loop converges only with an exception list, when reviewing a diff that clears a failure, or when reporting a phase complete with a workaround inside it. For finding the defect itself, load diagnosing-bugs."
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

For **each fix you propose**, write the chain **before the edit**, in the plan or the report.
It is an induction: three questions, asked again on their own answer, until the answer stops
being about this code.

1. **Why is this fix needed?** What was observed, and what the fix answers. Error text is
   allowed here and nowhere else.
2. **What caused the issue the fix answers?** The *decision* it came from: a line that
   chose, a check that classifies, a design that assumed. A cause is a verb with a subject.
   "The names collide" is a noun and stops short; "the loop decides the layer from the
   finding code and a stall count" is a decision and arrives.
3. **How could that issue have been prevented?** Name the prevention. It is a fix too — so
   return to step 1 and ask why *it* would be needed.

Continue until step 2 yields a **core property of the problem**: a statement that would still
be true if the code were rewritten from scratch, because it is about what the problem *is*,
not how this repo handles it. The prevention at that level is the fix. Everything the chain
passed on the way down is handling.

The **stop test** for a core property: rewrite the component in your head from nothing.
If the statement still holds, you have reached bottom. If a different design would make it
false, it is a property of the design, and the chain has one more turn in it.

Number the steps, and keep the questions visible in the text. The reader checks the *form* of
each link — decision or noun, prevention or apology — and needs no domain to do it. A chain
that ends at a noun, contains error text past its first line, or stops at a property of this
code is sent back on its form.

Two rules follow from the chain and are worth stating:

- **Chains that meet are one fix.** When several proposed fixes bottom out on the same
  property, that property is the finding, and the fixes above it are either the same change
  seen from different files or handling of what that change removes. Say which.
- **A cause predicts.** A core property explains more than the failure it was found through.
  Name one other thing it causes today, or one thing the fix makes pass without touching it,
  and run that. A story that explains exactly the one symptom is a description wearing a
  cause's clothes.

A compact example, so the shape is unmistakable. The fix under judgment: *make the repair
agent's verdict an input to the waiver decision.*

1. Why needed? The waiver node decides "source defect" from a finding code and a stall
   count, and neither says which layer is wrong.
2. What caused that? Those were the only signals that crossed rounds when it was written;
   the repair verdict was added later, for the operator to read, and was never wired in.
3. Prevent? Wire it in. — Why would that be needed? Because the loop needed *some* signal
   for "impossible from here", and used stall as the proxy.
2. What caused the need for a proxy? The checker emits the identical finding whether the
   book is wrong or the source is, so the loop cannot tell "not applied yet" from
   "impossible here".
3. Prevent? Emit findings that say which layer. — Why is that not already so?
2. Because the checker reads one representation, and the finding is a claim about the
   *correspondence* of two. **Core property:** fault cannot be assigned from one side of a
   correspondence. Rewrite the checker from scratch and it still holds.
3. Prevent? A finding of this class is born with fault *undetermined*, and only an
   observation of the other side may set it. The stall counter, the waiver, the seed and the
   routing are the apparatus built around a guess, and this is the line they sit above.

## Shape tests

Flat reference. Ask each of your own chain; a *yes* means it has not reached bottom. They are
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
  docstring calls it a doc defect, a consumer treats it as a code defect? Each author saw one
  case of an under-determined thing, and the under-determination has no representation. The
  missing representation is the origin, not either docstring.
- **Exactly one failure.** Does your explanation cover the one failure you saw and predict
  nothing else? A cause predicts; see the chain.
- **Convergence by exception.** Does the loop terminate only because a list of cases is
  excluded from it? Then the list is the finding, and it grows on every run.
- **Handling, routing, reporting.** Is the work improving where the case's paperwork goes —
  a tidier waiver, a better-placed IOU, a clearer log — rather than the number of cases?
  Improving the apology is the most comfortable form of the symptom fix, because the change
  is real and worth having, and the phase feels done.
- **"Cannot be fixed here."** Does the claim come without naming *where* it can be fixed, and
  whether the evidence to fix it already exists somewhere in the repo? Unreachable is a
  location, not a feeling.
- **A stored fact with no observation.** Does the fix record a claim about a changing world
  — a waiver, a cached verdict, a "known flaky" — without the observation that grounds it and
  the check that would find it stale? A cache with no invalidation is false at an unknown
  time.

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
that way is a **debt**, and it carries its chain with it: the chain above, down to the core
property it is *not* fixing, and why that property is out of reach from here. Write that
beside the hatch — in the waiver entry, the skip reason, the IOU text, the report — so the
next reader finds the cause where they find the workaround.

Having to write the chain down is what most often turns the hatch back into a fix. That is
the point, and it is why the writing comes before the edit rather than after.

A hatch also needs its **exit**: what removes it, and what checks that it was removed. A
waiver nobody deletes pre-waives the next genuine occurrence at the same spot; a skip nobody
revisits is a test that used to exist. Name the condition under which the hatch goes, and the
gate that will notice when it has.

## Completion criterion

The work is done when every line below is true, and each is checkable from the diff and the
report alone:

- Every proposed fix has its chain in the report, numbered, ending at a core property that
  passes the stop test, with the prevention at that level named.
- Fixes whose chains meet are reported as one, and the report says which of the rest are
  handling.
- Every hatch the diff adds or extends carries its chain and its exit beside it.
- The prediction was run — the other consequence was observed, or the untouched thing now
  passes — and the result is in the report.
- A phase reported complete names every hatch still standing inside it, or says there are
  none.

A phase with a hatch in it and no chain is not complete. It is a phase that improved the
routing of an apology.

## Reviewing someone else's fix

The same tests, applied to a diff you did not write. Read the failure it clears, then write
the chain the author did not: why the diff is needed, what caused that, what would have
prevented it. Where your chain goes deeper than the diff, the gap is the review finding. A
diff that touches a waiver file, a skip marker, a retry count or a broader `except` with no
chain in the description is the finding before any test is run. [[code-review]] carries the
rest of the review; this is the part that decides whether the fix is one.
