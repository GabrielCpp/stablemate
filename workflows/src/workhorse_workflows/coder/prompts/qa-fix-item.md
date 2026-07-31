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
to guess which item to check, and do not substitute a different one. If the path is blank or
the file does not exist, return `blocked` and say so.

## Required Context

Read:

- `AGENTS.md`
- `{{ instruction_ref("developer") }}`
- the story file, for its acceptance criteria
- the plan artifacts under the spec directory (`plan-context.json` names the services the
  fix touched — verify those, not the whole repository)
- the testing instruction files for the layers the fix touched, from those this repository
  installs: {{ instruction_refs("go-testing", "react-router-qa", "flutter-testing") | default("(none installed — follow the conventions the layer's existing tests establish)", true) }}

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

## Return Format

Return this exact JSON object as the LAST thing in your final response — these keys at its
top level, with no wrapper object around them. Any other shape fails to parse and the node
is retried:

```json
{"status": "passed|failed|blocked", "notes": "what you ran, what you observed, and what remains"}
```

- `status`: `passed` when every acceptance criterion is verified by something you actually
  ran; `failed` when the fix is wrong or incomplete; `blocked` when the environment, a
  credential or a missing service stopped you from checking at all. A criterion you could
  not exercise is never a pass.
- `notes`: one paragraph — the commands run, the observations, and for a non-pass the
  specific defect or the missing dependency. This text is handed verbatim to the single
  retry that follows, so it has to be enough to act on.
