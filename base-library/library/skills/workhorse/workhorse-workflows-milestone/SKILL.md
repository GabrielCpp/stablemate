---
name: workhorse-workflows-milestone
description: "Writing the milestone folder consumed by the Workhorse Author workflow: one durable release contract in `docs/milestones/<slug>/milestone.md`, its grill records, mockups and design links, and the ready gate Author enforces. Load when creating or reviewing a milestone, grilling one, or deciding whether a proposed milestone is ready for Author."
applyTo: "**/docs/milestones/*/milestone.md"
tags: [planning, docs]
---

# Author milestones

A milestone is the durable source contract for one release outcome:

```text
one milestone -> ordered epics -> vertical stories
```

It tells Author what the release must make true and which decisions every decomposition
must preserve. It does not perform the decomposition itself. Epics group coherent user
journeys in coding order. Stories are the vertical increments that deliver them.

## The boundary

Write one milestone when all of its scope has one release gate. Internal phases,
architecture layers, migrations, and rollout steps stay inside that milestone as epics or
stories. If two parts can ship, be accepted, and be declared done independently, they are
two milestones.

The reverse test catches a milestone that is too small:

> If this shipped by itself, could a user or operator recognize a completed product
> outcome?

If the answer is "no, but it prepares the next milestone," it is implementation work inside
a larger milestone.

## Folder contract

A milestone is a folder, `docs/milestones/<slug>/`. A flat `docs/milestones/<slug>.md` file
is a doctor error.

```text
docs/milestones/<slug>/
  milestone.md          required
  grills/<topic>.md     optional, one recorded grill tree per topic
  mockups/<journey-slug>.html   one per journey through a web or mobile book
  artifacts/            optional, anything
```

`ostler doctor` reads `milestone.md` and the mockup file names. It does not load `grills/`
or `artifacts/`, so those files need no frontmatter.

`milestone.md` carries this frontmatter and these sections:

```markdown
---
type: milestone
title: Local Formula and Report Engine
status: proposed
---

# Local Formula and Report Engine

## Outcome

## Release Boundary

## User Journeys

## Architecture Decisions

## Constraints

## Acceptance

## Non-Goals
```

Every section above needs prose. `## Compatibility Sources` is optional. Add it for a
rewrite, migration, or parity release, and omit it for new work. The optional frontmatter
keys are `id` (defaults to the folder name), `dependsOn`, `sourceItems` and `epics`. The
epic split writes `epics`, so leave it empty.

`## Architecture Decisions` records only decisions already made. A `## Open Decisions`
section is a doctor finding, so settle each decision into the right section and delete the
heading before approval.

Status vocabulary:

| Status | Meaning |
| --- | --- |
| `proposed` | Being researched or reviewed. Author must not consume it yet. |
| `approved` | Release boundary and decisions are settled. Ready for Author. |
| `authored` | Author produced valid epics and stories from it. |
| `delivered` | The milestone passed and the release outcome is available. |
| `superseded` | Another named milestone replaced this contract. |

Exactly one milestone in a docs root is `approved` at a time. Only the workflow advances
`approved` to `authored`, and only release completion advances it to `delivered`. A writer
may set `proposed` and, after explicit human approval, `approved`.

## What each section carries

### Outcome

State the actor-visible or operator-visible change in two short paragraphs: what becomes
possible, what is replaced, and why the release matters. Name the system boundary, not the
implementation sequence.

### Release Boundary

Say explicitly that this is one milestone and name the gate that makes it complete.
Separate what must coexist at cutover from work that may land incrementally. If the first
story has a mandatory walking-skeleton shape, state the one end-to-end journey it proves.
Do not list setup stories.

### User Journeys

Use one `###` section per journey. Each journey starts with a services bullet:

```markdown
### Sign in with a code

- services: web-app, api-service
```

The bullet lists the books under `docs/services/` that the journey goes through. Doctor
rejects a journey with no bullet and a book that does not exist.

Each journey also names:

- the actor and entry point;
- ordered observable steps;
- the outcome;
- required online, offline, empty, stale, failure, permission, or recovery states;
- preservation requirements when an existing journey is replaced.

The journey stays readable without source paths. Put implementation evidence in the
decision or compatibility sections instead.

A journey that goes through a book whose runbook driver is `web` or `mobile` needs a
mockup at `mockups/<journey-slug>.html`. The journey slug is the heading lowercased, with
every run of non-alphanumeric characters replaced by `-` and the edges trimmed, so
`Sign in with a code` becomes `sign-in-with-a-code`.

Author also requires a story-local mockup for each story that lists such a book in its
`services`. A story whose mockup fails is blocked, and the completion gate lists it with the reason.

### Architecture Decisions

Record choices that materially constrain more than one epic: ownership boundaries,
trusted and untrusted components, data placement, protocol shape, compatibility policy,
and retirement and cutover rules. Give enough of the reason to stop Author from choosing
the tempting wrong alternative.

Do not turn this section into a proposed file tree, class list, endpoint inventory, or task
sequence. Those are planning outputs downstream of the milestone.

### Compatibility Sources

Name the behavioral oracle first. Then name the code, fixtures, running systems,
screenshots, or prior attempts that provide evidence. Distinguish reusable techniques from
accidental behavior. Known defects in a reference implementation are decisions to resolve
against the oracle, not behavior inherited by silence.

Every external path or URL must be reachable by the Author run. If the source sits outside
the target checkout, include that checkout in the run's workspace or copy durable,
license-compatible fixtures into the target repository. A path the workflow cannot read is
not evidence.

### Constraints

List hard rules that every epic and story must preserve. A constraint earns a line when a
plausible implementation would violate it: no schema changes, one authorization boundary,
offline behavior, exact arithmetic, bounded resource use. Generic engineering advice stays
out.

### Acceptance

Define the milestone gate in observable terms. Cover every journey and every cross-cutting
decision, including cutover and removal evidence. Acceptance says what a reviewer can prove
in the running system or its produced artifacts, not which classes or files exist.

Do not pre-write story acceptance criteria. Several stories may contribute evidence to one
milestone line, and Author decides where each line lands.

### Non-Goals

Name tempting adjacent outcomes that this milestone deliberately does not deliver. A
non-goal must narrow a realistic interpretation of the outcome. Do not catalogue unrelated
features.

## Grill records

The session writes each settled grill tree into `grills/<topic>.md`. A record keeps the
questions asked, the answers chosen and the reason, so Author and later readers can see why
a decision holds. The record is plain markdown. Epic splitting reads the folder, so a
decision that matters to decomposition belongs in `milestone.md` as well.

`grills/pm.md` is the exception. The PM writes it as its ledger of answers to the writers' gaps.
The human may edit it, and an edit overrules the PM's answer. Do not file a grill topic under that name.

## Design links

Decompose notes stay in `docs/design/`. `milestone.md` links them with a relative path such
as `../../design/sign-in.md`. Doctor checks that every relative link in `milestone.md`
resolves to a file, and the epic split reads the notes it links.

## What stays out

- **No epic or story list.** Author owns decomposition and coding order.
- **No implementation checklist.** A bullet such as "create the bucket" is not a release
  outcome and biases Author toward horizontal stories.
- **No multiple release phases.** MVP, phase two, and later release gates are several
  milestones. Split them into folders.
- **No story-spec material.** Per-story plans, reviews, QA plans, and evidence belong in the
  story's spec folder (`ostler path spec <story>`) after Author has written the story.
- **No unresolved choice disguised as flexibility.** "Use Datastore or Cloud Storage" is an
  open decision. Settle it with the owner before the milestone leaves `proposed`.

## Session order

1. Write `milestone.md` from research on the current journey, target behavior, reference
   implementations, and deployment boundary. Every compatibility claim cites reachable
   evidence.
2. Grill it. Record each settled tree in `grills/<topic>.md` and fold the decisions into the
   sections they belong to.
3. Run decompose where a design is needed. Keep the notes in `docs/design/` and link them
   from `milestone.md`.
4. Write a mockup for each journey through a web or mobile book, at
   `mockups/<journey-slug>.html`.
5. Run `ostler doctor` and fix every milestone finding.
6. Present the milestone to the owner. Explicit approval sets `status: approved`. Silence
   is not approval.

## Ready gate

A milestone is ready when `ostler doctor` reports no milestone finding for it:

- every required section has prose;
- no `## Open Decisions` section remains;
- every relative link resolves;
- every journey has a services bullet that names existing books;
- every journey through a web or mobile book has its mockup;
- `status` is `approved` by the human owner, and no other milestone is `approved`.

Doctor reports these as warnings while the milestone is `proposed` and as errors once it is
`approved`, `authored` or `delivered`. Author runs the same check when it loads the
approved milestone and refuses to start on any error. It is a decomposer, not the authority
that invents the release boundary it is asked to decompose.
