---
name: stablemate-root-cause
description: "Judging whether a fix reaches a defect's origin or handles its symptom, with no knowledge of the domain: the why-chain written per fix before the edit (why is it needed, what decision caused that, how could it have been prevented — asked again on the prevention until the answer is a core property of the problem), the stop test for a core property, the shape tests that reject a story on its form, the unfixable-versus-unclassifiable question, and what a hatch carries when taken. Load when about to add or extend a waiver, retry, sleep, default, fallback, skip, broader except, null check or IOU, when a loop converges only with an exception list, when reviewing a diff that clears a failure, or when reporting a phase complete with a workaround inside it. For finding the defect itself, load diagnosing-bugs."
metadata:
  generated_by: farrier
  source: library/skills/root-cause/SKILL.md
  resolve: "farrier source .claude/skills/stablemate-root-cause/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
  tags: [standards, review]
---

# Root cause or symptom

[[diagnosing-bugs]] finds the defect. This skill judges the **fix**, and it fires on an action,
not a topic: the moment you reach for a waiver, retry, sleep, default, fallback, skip, broader
`except`, null check or IOU. Each is a **hatch**: the work converges without the case going away.

A hatch is sometimes right. What decides is not the domain — you may not know it — but the
**shape** of the story behind it. A sound causal story has a fixed form; an unsound one fails
that form before anyone judges whether it is true. This skill carries no evidence. It tells you
what a cause *looks like*, so you can check reasoning with nothing but the reasoning in hand.

## The chain

For **each fix you propose**, before the edit, in the plan or the report:

1. **Why is this fix needed?** What was observed. Error text goes here and nowhere else.
2. **What decision caused that?** A line that chose, a check that classified, a design that
   assumed. A cause is a verb with a subject: "the names collide" is a noun and stops short;
   "the loop decides the layer from a finding code and a stall count" arrives.
3. **How could it have been prevented?** Name the prevention. It is a fix too — return to
   step 1 with it, and run it through the shape tests as if it were already a diff.

Recurse until step 2 yields a **core property of the problem**: true of what the problem *is*,
not of how this code handles it. The prevention at that level is the fix; everything the chain
passed on the way down is handling.

**Stop test.** Rewrite the component from scratch in your head. If the statement still holds,
you have reached bottom. If a different design would make it false, the chain has one more turn.

**The last prevention is the one that gets built, and the one nothing has tested.** Every turn
judges the prevention above it; the terminal one is judged only if you aim the tests at it.
State it as a change — the artifact it edits, the state or branch it adds — while it is still
cheap to change.

Number the steps and keep the questions visible. The reader checks each link's *form* —
decision or noun, prevention or apology — and needs no domain to do it. A chain ending at a
noun, carrying error text past its first line, or stopping at a property of this code goes back.

- **Chains that meet are one fix.** Several fixes bottoming out on the same property are one
  change seen from different files, or handling of what that change removes. Say which.
- **A cause predicts.** Name one other thing the property causes today, or one thing the fix
  makes pass untouched, and run it. A story that explains exactly one symptom is a description.

### Example

Setup: a checker compares a document against the source it describes; a loop decides which of
the two to repair. The fix under judgment: *feed the repair agent's verdict into the waiver
decision.*

1. Why needed? The loop decides "source defect" from a finding code and a stall count; neither
   says which side is wrong.
2. What caused that? Those were the only signals crossing rounds when it was written; the
   verdict came later, for a human to read, and was never wired in.
3. Prevent? Wire it in. — Why would that be needed? The loop needed *some* signal for
   "impossible from here" and used stall as the proxy.
2. What caused the need for a proxy? The checker emits the identical finding whether the
   document or the source is wrong, so "not applied yet" and "impossible here" look the same.
3. Prevent? Findings that say which side. — Why not already?
2. The checker reads one representation, and the finding is a claim about the *correspondence*
   of two. **Core property:** fault cannot be assigned from one side of a correspondence.
   Rewrite the checker from scratch and it still holds.
3. Prevent? A finding is born with fault *undetermined*; only an observation of the other side
   may set it.

That is where this example first ended, and it is wrong — which is why it stays. Shape tests on
the terminal prevention: *A branch for the case* — a third value is a bucket the bad case travels
to, not one case fewer. *Legal in the target* — the document admits a claim only together with
its grounding, so "grounding unknown" is not a state it can hold. Legal in the language, illegal
in the artifact. So the chain turns once more:

2. What caused the document to hold one term? The field was specified to store the *value*
   observed, where every neighbouring field stores a *reference* to what produced it. A value
   can be transcribed; only a reference can be resolved. **Core property:** a copy is not
   evidence about its original.
3. Prevent? The field stores the reference and the checker resolves it. Fault is determined
   where the finding is made, and the stall count, the waiver and the routing above it have
   nothing left to classify.

## Shape tests

Ask each of your own chain. A *yes* means it has not reached bottom. None needs the domain.

- **Downstream.** Is the fix where the wrong value was *consumed*, not *produced*? A guard,
  default, wait, catch or waiver is a symptom fix until the chain shows the producer out of reach.
- **A branch for the case.** Does the diff route the bad case somewhere instead of removing it?
  A branch is a decision to live with it. Sometimes right; never the fix.
- **Legal in the target.** Does the fix add a state, field or value the artifact it edits does
  not admit? Quote the target's own rule — schema, type, invariant, docstring — and show the
  change satisfies it. Legal in the language but illegal in the artifact passes every type checker.
- **Fewer inputs than the distinction.** Does something decide A from B reading only what A and
  B share? Ask what you would have to *see* to tell them apart, then whether the decider reads it.
  Everything downstream that papers over its output is evidence of this, not a feature.
- **Disagreement in writing.** Do two components describe the same signal differently — one
  docstring says doc defect, a consumer treats it as code defect? Each author saw one case of an
  under-determined thing. The missing representation is the origin, not either docstring.
- **Exactly one failure.** Does the explanation cover the failure you saw and predict nothing
  else? A cause predicts.
- **Convergence by exception.** Does the loop terminate only because a list of cases is excluded?
  The list is the finding, and it grows every run.
- **Handling, routing, reporting.** Is the work improving where the case's paperwork goes — a
  tidier waiver, a better-placed IOU, a clearer log — rather than the number of cases? The change
  is real, so the phase feels done. Improving the apology is the most comfortable symptom fix.
- **"Cannot be fixed here."** Does the claim omit *where* it can be fixed, and whether the
  evidence already exists in the repo? Unreachable is a location, not a feeling.
- **A stored fact with no observation.** Does the fix record a claim about a changing world — a
  waiver, a cached verdict, a "known flaky" — without the observation that grounds it and the
  check that would find it stale? A cache with no invalidation is false at an unknown time.

## Unfixable or unclassifiable

**Is this case genuinely unfixable, or merely unclassifiable?** A pipeline that needs a hatch to
converge is usually facing not a stubborn defect but a distinction it cannot draw: two situations
emitting a byte-identical finding because the decider reads one layer and the difference lives in
the other. The evidence often already exists in the repo, unread — a build output the check never
consults, a trace the gate never opens, a second source the classifier never joins. Only an
unfixable case justifies a hatch. An unclassifiable one justifies reading the other layer.

Before reading the other layer, ask why the artifact does not already carry it. Reaching out is
right when the second observation genuinely lives elsewhere, and wrong when the artifact was
built to state it and records a transcription instead. That is *Downstream* one level up. A new
dependency on a live system, to decide something a document exists to state, is the signature.

## Taking the hatch anyway

When the origin is real, out of reach, and the work must converge now, the hatch is a **debt**.
It carries its chain — down to the core property it is *not* fixing, and why that is out of reach
from here — written beside it: the waiver entry, the skip reason, the IOU, the report. Having to
write the chain is what most often turns the hatch back into a fix, which is why the writing comes
before the edit.

It also carries its **exit**: the condition under which it goes, and the gate that notices when it
has. A waiver nobody deletes pre-waives the next genuine occurrence; a skip nobody revisits is a
test that used to exist.

## Completion criterion

Each line checkable from the diff and the report alone:

- Every proposed fix has its numbered chain, ending at a core property that passes the stop test,
  with the prevention at that level named.
- Every terminal prevention was put through the shape tests, including legal in its target.
- Chains that meet are reported as one fix, and the rest are labelled handling.
- Every hatch added or extended carries its chain and its exit beside it.
- The prediction was run, and the result is in the report.
- A phase reported complete names every hatch still standing, or says there are none.

A phase with a hatch and no chain is not complete. It improved the routing of an apology.

## Reviewing someone else's fix

Read the failure the diff clears, then write the chain the author did not. Where your chain goes
deeper than the diff, the gap is the finding. A diff touching a waiver, skip marker, retry count
or broader `except` with no chain in its description is the finding before any test runs.
[[code-review]] carries the rest; this decides whether the fix is one.
