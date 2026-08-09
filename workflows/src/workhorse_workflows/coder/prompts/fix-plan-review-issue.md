# Fix one blocking implementation-review issue

Fix exactly the checkpointed review issue below. The full source plan remains authoritative.

## Complete source plan

{{ workhorse_var('plan_text') }}

## Review issue

```json
{{ workhorse_var('issue') | tojson(indent=2) }}
```

Inspect the current repository first. Continue valid partial edits after a resumed interruption.
Change only the issue's declared paths. Make its acceptance statements true, add or correct tests as
needed, and run every verification command. Do not commit, push, modify the source plan, touch run
artifacts, change refs/remotes/Git configuration, or broaden scope. Deterministic workflow states
verify, commit, and publish the fix after this turn.

Return exactly one JSON object as the final response:

```json
{"status": "done|blocked", "notes": "what changed and what verification ran, or the blocker"}
```