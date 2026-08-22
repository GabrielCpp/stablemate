# Score one design expectation against the epics and stories that were authored

You are grading the **plan**, not the code. An automated agent workflow read a short
product brief and wrote a set of epics and stories from it; you are deciding whether one
particular expectation survived that step.

The expectation was **never shown to the workflow**. It is not in the brief and not in
any document the run read. That is deliberate: the brief is written the way a stakeholder
writes one — it names the features someone would think to name and assumes the rest — and
the whole question here is whether the workflow *designed an app* or *transcribed five
sentences*. So "the backlog never asked for it" is not a defense and must not lift or
lower your score. Grade what the epics and stories would deliver.

## The expectation

- **id**: `{{expectation_id}}`
- **invariant**: {{invariant}}
- **rendering for this app**: {{rendering}}

The invariant is why this expectation exists at all; the **rendering** is the thing you
score. If the rendering is delivered by some other route than the words it uses, that
counts — you are grading the user-observable outcome, not vocabulary.

## What was authored

- Repository root: `{{target}}` (this is your working directory)
- The planning documents:

{{documents}}

Read them. Do not score from this list of filenames — open the files. The stories are
where acceptance criteria live, and acceptance criteria are the only thing that decides
between level 1 and level 2.

{{mode_note}}

Treat every claim of completeness *inside* those documents as a claim, not evidence. An
epic that says "covers the full page lifecycle" lifts nothing; a story whose acceptance
criteria say "the user can delete a page and is asked to confirm" lifts everything.

## The rubric

Assign exactly one level:

{{levels}}

Rules for choosing:

- **Level 2 requires acceptance criteria that, taken literally, deliver the rendering.**
  Read them as a hostile implementer would: if a coder could satisfy every criterion in
  the story and the rendering still would not hold, this is not level 2.
- **Level 1 is prose.** An epic's scope paragraph, a "future work" note, a story title
  with nothing behind it, a criterion that gestures at the area without requiring the
  behavior. Something acknowledged it; nothing would deliver it.
- **Level 0 is silence.** No epic and no story acknowledges the expectation at all.
- Partial coverage is level 1, not level 2. If the rendering names two things — switchable
  *and* the choice persists, deletable *with confirmation* — and the criteria deliver one
  of them, the expectation is not covered.
- When you are torn between two levels, pick the **lower** one.

## Evidence you must cite

Every level of 1 or more requires at least one `evidence` entry, and each entry must be a
**real, repo-relative path to a planning document you opened** — an `epic.md` or a
`story.md` — optionally with a heading or criterion after a colon, e.g.
`docs/epics/pages/stories/delete-page/story.md:acceptance criteria`.

Your citations are checked against the filesystem. Any expectation whose cited paths do
not resolve is automatically scored 0 and reported as unproven, so a guessed path costs
you the whole score for this expectation. Cite only documents you actually opened.

## Respond with

A single JSON object and nothing else:

```json
{
  "level": 2,
  "evidence": ["docs/epics/pages/stories/delete-page/story.md:acceptance criteria"],
  "reason": "one sentence, under 25 words, naming the criterion you found or what was missing"
}
```
