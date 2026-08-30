---
name: workflows-author-roadmap
description: "Writing the roadmap item consumed by the Workhorse Author workflow: one durable release contract maps to exactly one milestone, names the user journeys and locked decisions that bind every epic, and leaves epic/story decomposition to Author. Load when creating or reviewing `docs/roadmaps/*.md`, replacing backlog intake with roadmap input, or deciding whether a proposed roadmap is ready for Author."
applyTo: "**/docs/roadmaps/*.md"
tags: [planning, docs]
---

# Author roadmap items

A roadmap item is the durable source contract for one release outcome:

```text
one roadmap item -> one milestone -> ordered epics -> vertical stories
```

It tells Author what the release must make true and which decisions every decomposition
must preserve. It does not perform the decomposition itself. Epics group coherent user
journeys in coding order; stories are the vertical increments that deliver them.

## The boundary

Write one roadmap item when all of its scope has one release gate. Internal phases,
architecture layers, migrations, and rollout steps stay inside that milestone as epics or
stories. If two parts can ship, be accepted, and be declared done independently, they are
two roadmap items rather than two milestones hidden inside one file.

The reverse test catches an item that is too small:

> If this shipped by itself, could a user or operator recognize a completed product
> outcome?

If the answer is "no, but it prepares the next item," it is implementation work inside a
larger roadmap, not a roadmap item.

## File contract

Roadmap items live at `docs/roadmaps/<slug>.md`. The repo-relative path is their stable
source identity until the planning graph assigns another one; never invent an id by hand.

```markdown
---
type: roadmap
title: Local Formula and Report Engine
status: proposed
---

# Local Formula and Report Engine

## Outcome

## Release Boundary

## User Journeys

## Architecture Decisions

## Compatibility Sources

## Constraints

## Acceptance

## Non-Goals
```

`Compatibility Sources` is required for a rewrite, migration, or parity release and may be
omitted for genuinely new work. `Architecture Decisions` records only decisions already
made; unresolved product choices go in `Open Decisions`, and an item with any open decision
remains `proposed`.

Status vocabulary:

| Status | Meaning |
| --- | --- |
| `proposed` | Being researched or reviewed; Author must not consume it yet. |
| `approved` | Release boundary and decisions are settled; ready for Author. |
| `authored` | Author produced a valid milestone, epics, and stories from it. |
| `delivered` | The milestone passed and the release outcome is available. |
| `superseded` | Another named roadmap item replaced this contract. |

Only the workflow advances `approved` to `authored`; only release completion advances it to
`delivered`. A writer may set `proposed` or, after explicit human approval, `approved`.

## What each section carries

### Outcome

State the actor-visible or operator-visible change in two short paragraphs: what becomes
possible, what is replaced, and why the release matters. Name the system boundary, not the
implementation sequence.

### Release Boundary

Say explicitly that this item is one milestone and name the gate that makes it complete.
Separate what must coexist at cutover from work that may land incrementally. If the first
story has a mandatory walking-skeleton shape, state the one end-to-end journey it proves;
do not list setup stories.

### User Journeys

Use one `###` section per journey. Each journey names:

- the actor and entry point;
- ordered observable steps;
- the outcome;
- required online, offline, empty, stale, failure, permission, or recovery states;
- preservation requirements when an existing journey is replaced.

The journey remains readable without source paths. Put implementation evidence in the
decision or compatibility sections instead.

### Architecture Decisions

Record choices that materially constrain more than one epic: ownership boundaries,
trusted and untrusted components, data placement, protocol shape, compatibility policy,
and retirement/cutover rules. Explain enough of the reason to prevent Author from choosing
the tempting wrong alternative.

Do not turn this section into a proposed file tree, class list, endpoint inventory, or task
sequence. Those are planning outputs downstream of the roadmap.

### Compatibility Sources

Name the behavioral oracle first, then the code, fixtures, running systems, screenshots,
or prior attempts that provide evidence. Distinguish reusable techniques from accidental
behavior. Known defects in a reference implementation are decisions to resolve against the
oracle, not behavior inherited by silence.

Every external path or URL must be reachable by the Author run. If the source sits outside
the target checkout, include that checkout in the run's workspace or copy durable,
license-compatible fixtures into the target repository; a path the workflow cannot read is
not evidence.

### Constraints

List hard rules that every epic and story must preserve. A constraint earns a line when a
plausible implementation would violate it: no schema changes, one authorization boundary,
offline behavior, exact arithmetic, bounded resource use. Generic engineering advice is a
no-op and stays out.

### Acceptance

Define the milestone gate in observable terms. Cover every journey and every cross-cutting
decision, including cutover and removal evidence. Acceptance says what a reviewer can prove
in the running system or its produced artifacts, not which classes or files exist.

Do not pre-write story acceptance criteria. Milestone acceptance is broader: several
stories may contribute evidence to one line, and Author decides where each line lands.

### Non-Goals

Name tempting adjacent outcomes that this milestone deliberately does not deliver. A
non-goal must narrow a realistic interpretation of the outcome; do not catalogue unrelated
features.

## What stays out

- **No epic or story list.** Author owns decomposition and coding order.
- **No implementation checklist.** A bullet such as "create the bucket" is not a release
  outcome and biases Author toward horizontal stories.
- **No multiple release phases.** A roadmap with MVP, phase two, and later release gates is
  a portfolio document containing several roadmap items. Split it.
- **No backlog-item identities.** The roadmap itself is the source; its sections are not
  independently pruned work items.
- **No story-spec material.** Per-story plans, reviews, QA plans, and evidence belong under
  `docs/specs/<story>/` after Author has written the story.
- **No unresolved choice disguised as flexibility.** "Use Datastore or Cloud Storage" is
  an open decision, not an architecture decision. Move it to `Open Decisions` and keep the
  roadmap proposed.

## Writing procedure

1. Research the current journey, target behavior, reference implementations, and deployment
   boundary. Completion: every factual compatibility claim cites reachable evidence.
2. State the single outcome and release gate. Completion: splitting the file at any heading
   would not produce two independently releasable outcomes.
3. Write all user journeys and required states before architecture. Completion: every
   acceptance line traces to a journey or a cross-cutting decision.
4. Record locked decisions, constraints, compatibility sources, and non-goals. Completion:
   no open product decision remains outside an explicit `Open Decisions` section.
5. Audit for decomposition leakage. Completion: there is no epic list, story list,
   layer-by-layer phase plan, or setup checklist.
6. Review with the owner. Completion: explicit approval changes `status` from `proposed` to
   `approved`; absence of a reply is not approval.

## Ready-for-Author gate

A roadmap is ready only when all are true:

- it has one release outcome and one milestone gate;
- every applicable user journey and required state is present;
- architecture decisions choose rather than offer alternatives;
- compatibility authority and reachable evidence are explicit;
- acceptance proves the whole release, including retirement/cutover work;
- non-goals prevent the plausible scope expansions;
- no open product decision remains;
- no epic, story, or horizontal implementation split has been pre-authored;
- status is `approved` by the human owner.

If any check fails, improve the roadmap or ask the owner. Author is a decomposer, not the
authority that invents the release boundary it is asked to decompose.
