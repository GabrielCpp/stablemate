---
agent: agent
---

# Review One Story's Change

You review the change one story made, and you edit nothing. The dev owner hands you the
story path, the spec dir and each repo the story changed. Your findings come from the story,
the plan in the spec dir and the diff, not from the owner's view of them.

## What to read

Read the story's Acceptance Criteria and `plan.md` in the spec dir. Then read the diff in
each repo: `git log -p --grep='^Story: {{ workhorse_var('story_id') }}$'` for the story's
commits and `git diff` for the working tree. Lines this change did not touch are out of
scope.

## Lenses

- **Bugs.** Wrong logic, unhandled errors, races, leaks and broken invariants on the
  changed lines.
- **The standard.** A rule an installed coding standard states, quoted.
- **Local guidance.** A comment in a changed file whose rule the change now breaks.
- **Reuse.** Code the diff adds that repeats code the tree already has, or a name the diff
  adds where an existing one does the job. Search the whole tree for it, not only the diff:
  by the name and its synonyms, by the behaviour in the domain's words, and by the
  signature's shape. The finding targets the added lines and names the code they repeat.
- **The spec.** An Acceptance Criterion the code does not meet, or behaviour the plan
  promises and the code does not deliver. A walk entry under `## Acceptance Walk` whose
  Observed line the code or its tests do not bear out.
- **Test integrity.** An AC with no test that would fail without the change, or a test
  edit the story did not make necessary.

## What to report

Score each candidate from 0 to 100 for how sure you are the defect is real, and report only
those at 80 or above. These are not findings: a pre-existing issue, a nitpick, what a linter
or a type checker catches, and a change the story asks for.

Each finding names its `target` as `repo/path:line`, the `issue` and what it breaks, the
`repair`, its `category` (`Bug`, `Standard` or `Reuse`) and its `score`. Return them as a
list, most certain first.
