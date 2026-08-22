# Walk one persona journey, on paper, through the epics and stories that were authored

You are grading the **plan**, not the code. An automated agent workflow read a short
product brief and wrote a set of epics and stories from it. Your job is to walk one
scripted journey through those documents, step by step, and count the steps no story
delivers.

The journey was **never shown to the workflow**, and neither was the list of things it
expects. That is deliberate: a checklist catches only what someone thought to list, and
the failure this metric exists to catch is incoherence — a screen nothing links to, a
control that exists on one screen and not the one that needs it, a step that falls
between two stories that each assumed the other had it.

So "the backlog never asked for this step" is not a defense. A person following this
journey either can complete the step with what the stories deliver, or they cannot.

## The journey

- **id**: `{{journey_id}}`
- **persona**: {{persona}}
- **steps**, in order:

{{steps}}

## What was authored

- Repository root: `{{target}}` (this is your working directory)
- The planning documents, and the only thing you may walk through:

{{documents}}

Read them. Open the story files — acceptance criteria are what decide a step, and a story
title is not one.

## Deciding a step

A step is **delivered** when a story's acceptance criteria, taken literally, would give a
person the thing the step needs at the moment the journey needs it. Read as a hostile
implementer: if a coder could satisfy every criterion and the person walking this journey
would still be stuck at this step, the step is a **dead end**.

Specifically, a step is a dead end when:

- no story covers it at all; or
- a story covers the capability but not from where the journey is standing — the control
  exists on a screen this journey never reaches, or the screen has no route into it other
  than typing a URL; or
- the criteria mention the area but require no behavior a person could use.

Judge each step independently, but in the order given: a step may rely on state an earlier
step established. An earlier dead end does not automatically make the rest dead ends —
score each on whether the stories would deliver it.

## Evidence you must cite

Every step you mark delivered requires at least one `evidence` entry: a **real,
repo-relative path to a planning document you opened** (`epic.md` or `story.md`),
optionally with a criterion after a colon. Citations are checked against the filesystem,
and a delivered step whose citations do not resolve is counted as a dead end.

A dead end needs no citation — say what was missing in `why`.

## Respond with

A single JSON object and nothing else, with one entry per step, in order:

```json
{
  "steps": [
    {
      "step": "sign in with an email address and a password",
      "delivered": true,
      "evidence": ["docs/epics/accounts/stories/sign-in/story.md:acceptance criteria"],
      "why": "under 20 words"
    },
    {
      "step": "sign out",
      "delivered": false,
      "evidence": [],
      "why": "no story mentions ending a session"
    }
  ]
}
```
