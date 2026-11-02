---
name: workhorse-workflows-author-session
description: "Authoring a milestone's epics and stories live in a session with its owner, as the interactive alternative to the Author workflow: an epic split in coding order, vertical slices per epic, a stateful mockup per story, story prose a coder run can build unattended, and a fresh reader per epic. Ends in the same artifacts Author writes. Load when the owner wants to author an approved milestone by hand, when asked to split a milestone into epics or stories in conversation, or when a run of the Author workflow would cost more than the owner's attention. For writing the milestone itself, load workhorse-workflows-milestone."
tags: [planning, docs]
---

# Author a milestone in a session

The session writes what the Author workflow writes: epics and stories in the planning graph,
with a mockup per story that changes a screen. A coder run launched on a named epic cannot
tell the two apart. The owner's judgement replaces the workflow's reviewers at two
checkpoints.

Start from a milestone with `status: approved`. A milestone still `proposed` goes through
[[workhorse-workflows-milestone]] first.

## The two pacing modes

**Checkpointed** is the default. The session stops for acceptance after the epic split and
after each epic's slices.

**Auto-accept** applies once the owner says they will review only the outcome. Each proposal
stands as written, and the session runs to the end. Every choice a checkpoint would have
surfaced goes into the final report, with its reason.

A conflict inside the milestone stops both modes. It goes to the owner as one question with a
recommendation, because the milestone is theirs.

## Steps

### 1. Ground

Read the milestone, its grills, every design note it links and its journey mockups. Search the
book with `ostler search` and `ostler trace` for each surface a journey changes, then read the
source behind those surfaces.

Done when every journey step has a book node it changes and the source symbols that serve it.

### 2. Split into epics

Propose ordered epics, each one a coherent journey an actor can recognize as finished. Put a
removal in the same epic as its replacement, so no epic leaves a surface missing. State what
each epic leaves for a later one.

Done when every milestone journey and acceptance line has an epic that delivers it. This is the
first checkpoint.

### 3. Author each epic, in order

**Slice.** Load [[vertical-slicing]]. Write each story's answer to "what can the actor do after
this that they could not do before?" A dependency exists only where a story widens a path
another story opened. This is the second checkpoint.

**Create.** Add seeds with `ostler seed add` and stories with `ostler create story`, in the
order of the slices. Ostler owns `## Seeds` and `## Stories`, and it allocates every id. Each
seed names its surface as a book node, and its backing as the data that serves it.

**Mock.** A story that changes a screen gets a `mockup.html`. Read
[references/mockups.md](references/mockups.md) before the first one, and when a rendered state
looks wrong.

**Write.** Add the epic's prose above `## Seeds` and fill each story, to the bars below.

**Check.** `ostler doctor` raises no finding on the epic, and every active seed is covered.
Findings that were there before the session stay out of the session.

**Read fresh.** Run the reader described below, and resolve what it finds.

### 4. Reconcile across epics

Read every epic's hand-offs against the next one. A promise such as "the strip lands in the
last epic" must appear as a criterion there. A definition shared across epics, such as what
counts as a problem, has one wording and one count. A figure a later story reuses is the
figure the earlier story defined.

Done when each hand-off resolves to a criterion by name.

### 5. Report

State the epics and stories in coding order, the choices taken under auto-accept and any
finding left open. The milestone stays `approved`, because the session leaves its status to the
owner.

## The epic bar

An epic carries `## User Outcome`, `## User Journeys`, `## Delivered Experience` with its
required states, `## Guardrails`, `## Non-Goals`, `## Acceptance` and `## Method`. The journey
steps come from the milestone word for word. A guardrail binds a plausible build that would
otherwise break it. Method says why the first story is the walking skeleton and why the last
story comes last.

## The story bar

A coder run builds the story with nobody to ask, so a reader who guesses builds something else.
Each story has four prose sections:

- **Context:** the actor's problem in their words, the book node this lands on as a link, the
  mockup as the source of truth, and what Done means.
- **Acceptance Criteria:** one observable check per line, each one decidable by looking at the
  running system. A state that can load has a criterion for it appearing and one for it
  clearing. A state that can fail says what stays usable, and a retry that succeeds clears it.
- **Non-Functional Acceptance Criteria:** invariants the story inherits, such as what must
  behave as it did, or `(none)`.
- **Technical Notes:** backticked `path::symbol` citations with a short clause each, read from
  the source and checked to exist. Each row or figure on a screen names the query, cursor or
  record behind it.

Keep ids and short handles out of documents, because a handle lengthens when ids collide.
Ground each criterion in the milestone or in a decision you can state. A guess that two builds
would resolve differently is a decision: settle it, and write it as a criterion or a guardrail.

## The fresh reader

The author of an epic cannot find what its argument hides, so a new agent reads it. Start a
fresh agent, never a fork. Give it the milestone, the sibling epics, the epic and its rendered
mockups, and none of the session's reasoning. Ask for defects in these classes:

1. A milestone requirement no story delivers, or a story the milestone rules out.
2. A criterion and a mock state that disagree, or either one without the other.
3. A criterion that cannot be checked in the running system.
4. A technical note that is wrong about the code.
5. A story that needs something a later story provides.
6. Numbers on one screen that do not add up, or a row that contradicts its detail.
7. A question where two reasonable builds show the actor different things.
8. A row or figure on a list with no named store behind it, or one that would need every run's
   files read on each load.
9. A status label with no mapping from the values the code writes. Read those values from the
   source, because one the story assumed may never occur and one it missed still reaches the
   screen.

Check each finding against the source or the render before acting, because a reader can be
wrong. Fix what holds, in the story and its mock together.

Done when each finding is fixed or refuted, and `ostler doctor` still passes.
