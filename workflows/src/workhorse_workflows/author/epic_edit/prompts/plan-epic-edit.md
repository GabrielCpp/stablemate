---
agent: agent
---

# Plan an edit to epic `{{ workhorse_var('snapshot').epic }}`

Plan only. Do not edit any file and do not run a mutating command. A deterministic node applies the
plan only after it passes static validation and an independent semantic review.

## Binding intent

{{ workhorse_var('intent') }}

## Current graph snapshot

{{ workhorse_var('snapshot') }}

## Required reading

- `{{ workhorse_var('epic_dir') }}/epic.md` and its current stories.
- The configured backlog at `{{ workhorse_var('backlog') }}`.
- Existing feature documentation under `{{ workhorse_var('features_dir') }}`; read only, never write.
- `{{ workhorse_var('epic_dir') }}/context.md` when present.

## Plan contract

- The intent is binding. An add must leave the requested source item covered; a remove must leave
  the requested story absent.
- Every active seed must be covered by at least one resulting story.
- Removing a story requires an explicit change for every seed or dependency it affects.
- `delete_epic` is true only when no seeds and no stories remain.
- Preserve unaffected stories. Put every added story, and every updated story whose body must change,
  in `affected_stories`.
- Use `seed_changes` actions `add`, `update`, or `remove`. A removal uses `disposition: drop` and a
  non-empty reason when product scope is intentionally removed.
- Use `story_changes` actions `add`, `update`, or `remove`. An add/update supplies the complete title,
  covers, and depends lists that should remain after the edit.
- The plan must update the epic's actor journeys, delivered experience, guardrails, acceptance, and
  non-goals wherever the change makes them stale.

## Final response

Return exactly one JSON object matching this shape:

```json
{
  "status": "complete" | "blocked",
  "epic": "existing epic name",
  "delete_epic": false,
  "summary": "resulting epic boundary",
  "journey_changes": ["specific journey change"],
  "seed_changes": [{
    "action": "add" | "update" | "remove",
    "id": "seed-id",
    "status": "researched",
    "summary": "one line",
    "surface": "documented surface or missing from OKF",
    "legacy_surface": "",
    "backing": "",
    "prerequisites": "none",
    "source_bullet": "verbatim source bullet",
    "disposition": "retain" | "drop",
    "reason": ""
  }],
  "story_changes": [{
    "action": "add" | "update" | "remove",
    "slug": "story-slug",
    "title": "Story title",
    "covers": ["seed-id"],
    "depends": ["sibling-story"],
    "rewrite": true
  }],
  "affected_stories": ["story-slug"],
  "notes": "blocking question or concise rationale"
}
```
