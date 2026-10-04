---
name: root-cause
description: "Judging whether a fix reaches a defect's origin or handles its symptom, with no knowledge of the domain: the why-chain written per fix before the edit (why is it needed, what decision caused that, how could it have been prevented, asked again on the prevention until the answer is a core property of the problem), the stop test for a core property, the shape tests that reject a story on its form, the unfixable-versus-unclassifiable question, and what a hatch carries when taken. Load when about to add or extend a waiver, retry, sleep, default, fallback, skip, broader except, null check or IOU, when a loop converges only with an exception list, when reviewing a diff that clears a failure, or when reporting a phase complete with a workaround inside it. For finding the defect itself, load diagnosing-bugs."
tags: [standards, review]
---

# Root cause or symptom

[[diagnosing-bugs]] finds the defect. This skill judges the **fix**. It fires on an action,
whatever the topic: the moment you reach for a waiver, retry, sleep, default, fallback, skip,
broader `except`, null check or IOU. Each of these is a **hatch**. A hatch lets the work
converge while the case stays.

A hatch is sometimes right. The **shape** of the story behind it decides, and the shape can be
judged without knowing the domain. A sound causal story has a fixed form. An unsound one fails
that form before anyone asks whether it is true. This skill carries no evidence. It tells you
what a cause *looks like*, so you can check a line of reasoning with only the reasoning in
hand.

## The chain

Write the chain for **each fix you propose**, before the edit, in the plan or the report:

1. **Why is this fix needed?** State what was observed. Error text goes here and nowhere else.
2. **What decision caused that?** A line that chose, a check that classified, a design that
   assumed. A cause is a verb with a subject. "The names collide" is a noun, and it stops
   short. "The loop decides the layer from a finding code and a stall count" arrives.
3. **How could it have been prevented?** Name the prevention. The prevention is a fix too.
   Return to step 1 with it, and run it through the shape tests as if it were already a diff.

Repeat until step 2 yields a **core property of the problem**: a statement true of what the
problem *is*, whatever code handles it. The prevention at that level is the fix. Everything
the chain passed on the way down is handling.

**Stop test.** Rewrite the component from scratch in your head. When the statement still
holds, the chain has reached bottom. When a different design would make it false, the chain
has one more turn.

**Aim the tests at the last prevention.** Every turn of the chain judges the prevention above
it, so the last one is judged only when you turn the shape tests on it. It is also the one
that gets built. State it as a change: the artifact it edits, and the state or branch it adds.
Do this while it is still cheap to change.

Number the steps and keep the questions visible. The reader checks the *form* of each link:
decision or noun, prevention or apology. That check needs no domain. A chain goes back when it
ends at a noun, carries error text past its first line, or stops at a property of this code.

- **Chains that meet are one fix.** Several fixes that bottom out on the same property are one
  change seen from different files, or handling of what that change removes. Say which.
- **A cause predicts.** Name one other thing the property causes today, or one thing the fix
  makes pass untouched, and run it. A story that explains exactly one symptom is a description.

### Example

The setup: a checker compares a document against the source it describes, and a loop decides
which of the two to repair. The fix under judgement: *feed the repair agent's verdict into the
waiver decision.*

First turn.

1. Why is it needed? The loop decides "source defect" from a finding code and a stall count.
   Neither says which side is wrong.
2. What decision caused that? Those were the only signals that crossed rounds when the loop
   was written. The verdict came later, for a person to read, and nobody wired it in.
3. How to prevent it? Wire the verdict in.

Second turn, on "wire the verdict in".

1. Why is it needed? The loop needed some signal for "impossible from here", and it used the
   stall count as a proxy.
2. What decision caused that? The checker emits the same finding whether the document or the
   source is wrong. "Not applied yet" and "impossible here" look the same.
3. How to prevent it? Findings that say which side is wrong.

Third turn, on "findings that say which side".

1. Why is it needed? Today's findings cannot say it.
2. What decision caused that? The checker reads one representation, and the finding is a claim
   about the *correspondence* of two. **Core property:** nobody can assign fault from one side
   of a correspondence. Rewrite the checker from scratch and the statement still holds.
3. How to prevent it? A finding is born with its fault *undetermined*. Only an observation of
   the other side may set it.

The example first ended there, and that ending is wrong. It stays in the example for that
reason. Two shape tests reject the last prevention:

- *A branch for the case.* A third value is a bucket the bad case travels to. The number of
  bad cases stays the same.
- *Legal in the target.* The document admits a claim only together with its grounding, so
  "grounding unknown" is a state the document cannot hold. The value is legal in the language
  and illegal in the artifact.

So the chain turns once more.

2. What decision made the document hold one side only? The field was specified to store the
   *value* observed. Every neighbouring field stores a *reference* to what produced it. A
   value can be transcribed, and only a reference can be resolved. **Core property:** a copy
   is not evidence about its original.
3. How to prevent it? The field stores the reference, and the checker resolves it. The fault
   is determined where the finding is made. The stall count, the waiver and the routing above
   it have nothing left to classify.

## Shape tests

Ask each one of your own chain. A *yes* means the chain has not reached bottom. None of them
needs the domain.

- **Downstream.** Is the fix where the wrong value was *consumed*, and not where it was
  *produced*? A guard, default, wait, catch or waiver is a symptom fix until the chain shows
  the producer is out of reach.
- **A branch for the case.** Does the diff route the bad case somewhere instead of removing
  it? A branch is a decision to live with the case. It is sometimes right, and it is never
  the fix.
- **Legal in the target.** Does the fix add a state, field or value that the artifact it edits
  does not admit? Quote the target's own rule, such as a schema, a type, an invariant or a
  docstring. Show that the change satisfies it. A change that is legal in the language and
  illegal in the artifact passes every type checker.
- **Fewer inputs than the distinction.** Does something decide A from B while reading only
  what A and B share? Ask what you would have to *see* to tell them apart. Then ask whether
  the decider reads it. Everything downstream that papers over the decider's output is
  evidence of this defect.
- **Disagreement in writing.** Do two components describe the same signal differently? One
  docstring says document defect, and a consumer treats the signal as a code defect. Each
  author saw one case of an under-determined thing. The origin is the missing representation.
  Neither docstring is.
- **Exactly one failure.** Does the explanation cover the failure you saw and predict nothing
  else? A cause predicts.
- **Convergence by exception.** Does the loop end only because a list of cases is excluded?
  The list is the finding, and it grows every run.
- **Handling, routing, reporting.** Does the work improve where the paperwork of the case
  goes, while the number of cases stays the same? A tidier waiver, a better-placed IOU and a
  clearer log are all real changes, so the phase feels done. Improving the apology is the most
  comfortable symptom fix.
- **"Cannot be fixed here."** Does the claim omit *where* the case can be fixed, and whether
  the evidence already exists in the repo? Unreachable is a location. Name it.
- **A stored fact with no observation.** Does the fix record a claim about a changing world,
  such as a waiver, a cached verdict or a "known flaky" mark? The record needs the observation
  that grounds it and the check that finds it stale. A cache with no invalidation becomes
  false at a time nobody knows.

## Unfixable or unclassifiable

Ask of every case that seems to need a hatch: **is it unfixable, or only unclassifiable?**

A pipeline that needs a hatch to converge usually faces a distinction it cannot draw. Two
situations emit the same finding, because the decider reads one layer and the difference
lives in the other. The evidence often sits in the repo already, unread: a build output the
check never consults, a trace the gate never opens, a second source the classifier never
joins. Only an unfixable case justifies a hatch. An unclassifiable case justifies reading the
other layer.

Before reading the other layer, ask why the artifact does not already carry that evidence.
Reaching out is right when the second observation lives elsewhere by nature. Reaching out is
wrong when the artifact was built to state the fact and records a transcription instead. That
is the *Downstream* test one level up. Its mark is a new dependency on a live system, added to
decide something a document exists to state.

## Taking the hatch anyway

Take the hatch when the origin is real, out of reach, and the work must converge now. The
hatch is then a **debt**, and it carries two things.

- **Its chain**, written beside it: in the waiver entry, the skip reason, the IOU or the
  report. The chain goes down to the core property the hatch is *not* fixing, and says why
  that property is out of reach from here. Writing the chain is what most often turns a hatch
  back into a fix. That is why the writing comes before the edit.
- **Its exit**: the condition under which the hatch goes, and the gate that notices when the
  condition holds. A waiver nobody deletes waives the next real occurrence in advance. A skip
  nobody revisits is a test that used to exist.

A hatch is one decision each time. When the same loop asks for a third hatch, the plan is in
question and the next fix is not the answer. Load [[step-back]].

## Completion criterion

Each line is checkable from the diff and the report alone:

- Every proposed fix has its numbered chain. The chain ends at a core property that passes the
  stop test, and it names the prevention at that level.
- Every last prevention went through the shape tests, including *Legal in the target*.
- Chains that meet are reported as one fix, and the rest are labelled handling.
- Every hatch added or extended carries its chain and its exit beside it.
- The prediction was run, and its result is in the report.
- A phase reported complete names every hatch still standing, or says there are none.

A phase with a hatch and no chain is not complete. It improved the routing of an apology.

## Reviewing someone else's fix

Read the failure the diff clears. Then write the chain the author did not write. Where your
chain goes deeper than the diff, the gap is the finding. A diff that touches a waiver, a skip
marker, a retry count or a broader `except`, with no chain in its description, is a finding
before any test runs. [[code-review]] carries the rest of the review. This skill decides
whether the fix is one.
