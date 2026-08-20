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
- this repo's developer / local-stack runbook: {{ find_by_tags("runbook") | default("(none installed — follow `AGENTS.md` and the repo's own documented commands)", true) }}
- the story file, for its acceptance criteria
- the plan artifacts under the spec directory. Verify the services the fix touched, not
  the whole repository:
{% if plan_services %}
{{ plan_services }}
{% endif %}
- the testing instruction files for the layers the fix touched, from those this repository
  installs: {{ find_by_tags("tests") | default("(none installed — follow the conventions the layer's existing tests establish)", true) }}

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

## Commit What You Wrote

The workflow does not commit on your behalf. Work still sitting in the working tree when the
story ends parks it for an operator instead of shipping it, so the last thing you do is record
what you wrote:

1. **Stage by explicit path** — never `git add -A`, `git add .` or `git commit -a`. Those sweep
   in whatever else is in the tree, and something else is usually working here. Anything that is
   not yours stays exactly where it is.
2. **One commit per repository**, its subject scoped to the package you changed:

   ```
   <type>(<package>): <lowercase imperative description>

{% if workhorse_var('epic') %}   Epic: {{ workhorse_var('epic') }}
{% endif %}{% if workhorse_var('story_slug') %}   Story: {{ workhorse_var('story_slug') }}
{% endif %}   ```

   `<type>` is `fix`: this commit repairs behaviour that was already there. Subject ≤ 72 characters, no capital first word, no
   trailing period. Keep the trailers exactly as spelled — they are how the run record ties a
   commit back to its story.
3. **Do not push, open a pull request, or switch branches.** The workflow owns those.

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
