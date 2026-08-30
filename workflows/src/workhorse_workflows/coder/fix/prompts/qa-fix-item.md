---
agent: agent
---

# QA A Drained Backlog Fix

You are the QA turn for one item drained off the backlog. There is no authored QA plan, no
ostler runner behind you and no evidence gate in front of you — **this turn is the whole
verdict on the fix**. Exercise the change yourself and report what you observed.

## Inputs (authoritative — do not rediscover)

- Story: `{{ workhorse_var('story_path') }}`
- Spec directory: `{{ workhorse_var('spec_dir') }}`
- QA directory: `{{ workhorse_var('qa_dir') }}`
- Target environment: `{{ workhorse_var('target_env') }}`

QA **only** the story at the story path above. Do not search the repository or git history
to guess which item to check, and do not substitute a different one.

## Required Context

Read:

- `AGENTS.md`
- the story file, for its acceptance criteria
- the plan artifacts under the spec directory. Verify the services the fix touched, not
  the whole repository:
{% if plan_services %}
{{ plan_services }}
{% endif %}
- the testing standards that govern the files the fix touched, failing that the
  conventions the layer's existing tests establish

## What To Do

1. Establish what the story claimed to fix, from its acceptance criteria.
2. Run the narrowest verification that proves it: the touched packages' tests, the layer's
   lint/analyze gate, and — for a user-visible change — the behavior itself.
3. Rule out the failures a green suite hides: a 5xx swallowed by the client, a console
   error, a partial write, a test that asserts presence rather than the behavior.
4. Confirm the fix stayed inside its scope — an item that quietly changed unrelated
   surfaces is a `failed` QA, not a pass.

Write or update `<spec_dir>/qa.md` with what you ran, what you observed and the acceptance
criteria each observation covers. Create it through `ostler` first — `timeout 30 ostler
create spec <story-name> qa.md`, where `<story-name>` is the folder name of `<spec_dir>` —
which stamps the `type: spec.qa` frontmatter that makes it an OKF Concept and leaves an
existing typed doc untouched. Write your content **below the `---` frontmatter block and
leave that block in place**; a doc with no `type:` is an `okf-missing-type` error against
the graph.

## Boundaries

Do not:

- fix what you find — a failing verdict is the answer, and the workflow owns the retry;
- weaken, skip or delete a test to reach a pass;
- broaden the check into unrelated repository debt. Pre-existing failures outside the
  fix's own surface are noted, not counted against it.

## Commit Identity

Every commit subject ends with `[{{ workhorse_var('story_id') }}]`, after its description.
Every commit also carries `Epic: {{ workhorse_var('epic') }}` and
`Story: {{ workhorse_var('story_id') }}` as trailers, spelled exactly so — the run record
ties a commit back to its story through them.

## Return Format

Return the JSON document as the LAST thing in your final response — its keys at the top level, with no wrapper object around them. Any other shape fails to parse and the node is retried.

{{ result_schema }}
