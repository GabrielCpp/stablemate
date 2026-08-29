---
agent: agent
---

# okf-builder: document one story change

Merge this changed source unit into the current as-built OKF contract. Work only in the
feature book under `{{ workhorse_var('features_root') }}`; source repositories are read-only.

Load and obey {{ skill_load_ref("ostler-okf", skill_dir() + "/ostler-okf/SKILL.md") }}.
Use the per-type references under
`{{ skill_path_ref("ostler-okf", "references/node-types") }}` and format touched documents.

## Story

- id: `{{ workhorse_var('story_id') }}`
- file: `{{ workhorse_var('story_path') }}`

{{ workhorse_var('story_content') }}

Acceptance criteria:

{{ workhorse_var('acceptance_criteria') }}

## Change

- target: `{{ workhorse_var('item_target') }}`
- exact context: `{{ workhorse_var('item_context') }}`
- docs root: `{{ workhorse_var('repo_root') }}`
- feature root: `{{ workhorse_var('features_root') }}`
- source checkout roots: `{{ workhorse_var('source_roots') }}`

Directly ground every changed nondeleted ref from the context using its exact `repo://`
spelling. Deleted refs are cleanup work, not positive coverage: remove stale grounding and
contract claims they no longer support. Merge into existing nodes rather than writing a
changelog, and materialize implemented user flows needed to state the story's current
as-built behavior.

Do not traverse unrelated source. Read only the named refs, their direct owning nodes, and
the minimum adjacent code needed to state their contract. If acceptance criteria and code
contradict each other, leave the contradiction visible and return `partial`; do not invent
behavior to reconcile them.

Return no follow-up crawl items. Produce JSON matching:

```json
{"discovered": [], "doc_status": "documented"}
```
