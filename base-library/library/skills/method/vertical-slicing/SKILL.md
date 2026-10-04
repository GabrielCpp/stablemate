---
name: vertical-slicing
description: "Tracer-bullet slicing of work into stories: the first story is a walking skeleton, the thinnest end-to-end path through every layer, observable in the running system. Every later story widens that path, and no story is a horizontal layer. Load when splitting an epic into stories, when ordering the work of a design into slices, or when reviewing a split."
tags: [planning]
---

# Vertical slicing: tracer bullets, not layers

A story earns its place by moving one **user-observable journey step** through the *whole*
stack. "Whole" is whatever this system has: UI to API to storage, CLI to engine to disk,
ingest to model to report.

A story that builds one layer for many future steps is a **horizontal** slice. "The data
model", "all the endpoints" and "the component library" are the usual names. A horizontal
slice costs three things:

- nobody can test it at the boundary of the running system,
- its integration risk moves to whichever story finally connects the layers,
- until that story lands, the epic has spent most of its budget and the actor can do
  nothing new.

## The first story is the walking skeleton

The first story of an epic is the root the other stories depend on. It is the **tracer
bullet**: the thinnest path that lets the epic's actor complete *one* real step of the
journey end to end, however small, in the running system.

- **Thinnest means minimum width at full depth.** One screen with one control, one
  endpoint, one table, one happy path, all of it wired for real. The control calls the
  real endpoint, the endpoint hits the real store, and the result shows where the actor
  stands. Hard-coded breadth is fine. A mocked layer is not. The skeleton exists to prove
  integration, and a skeleton with a fake spine proves nothing about it.
- **The setup rides along.** The project scaffold, the hosting, the schema baseline and
  the CI are work inside the first story, sized to what this one path needs. They are
  never enabler stories that come before it. When the setup feels too big to ride along,
  the skeleton is too wide. Narrow the path and keep the depth.
- **Its acceptance criterion is the actor's step.** The actor completes that step at the
  boundary of the running system, as in any other story.

## Every later story widens the skeleton

Order the stories so that each one **widens** a path that already runs: another journey
step, another entity, the error paths, the polish. Each story ends with the journey longer
or richer than the story before left it. Put one question to every proposed story:

> *After this story is green, what can the actor do that they could not do before?*

When the answer is "nothing yet, but the next story will be easier", the story is a
horizontal slice. Fold it into the earliest story whose journey step needs it.

## What this rules out

- A first story with no journey step of its own, such as "set up the backend", "create
  the data model" or "scaffold the frontend".
- A split ordered by layer: all the storage stories, then all the API stories, then all
  the UI stories. Its first end-to-end moment arrives in the final third.
- A dependency that exists only because "the layer below should be built first". A story
  depends on another when it widens a path that story opened.
- Deferred integration: a story whose deliverable runs only in a test harness, or behind
  a mock of a neighbouring layer that a sibling story builds for real.

## What this leaves open

- A widening story may sit mostly in one layer, when that is where the width is. The rule
  is that each story ends at an observable journey step. It does not ask every story to
  be equally deep.
- A technical enabler is a story when it directly unlocks a named journey step and has a
  boundary someone can observe from outside. Any other enabler rides inside the story
  that needs it.
- The skeleton may be ugly. Unstyled, unvalidated and single-user is fine. Width comes
  in the later stories.
