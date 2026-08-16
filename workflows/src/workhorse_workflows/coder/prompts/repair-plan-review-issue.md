# Repair a review-issue fix that failed deterministic verification

The previous fix attempt for this review issue did not pass. Correct the issue within its declared
paths and rerun its complete verification list.

## Complete source plan

{{ workhorse_var('plan_text') }}

## Review issue

```json
{{ workhorse_var('issue') | tojson(indent=2) }}
```

## Deterministic findings for repair {{ workhorse_var('repair') }}

{{ workhorse_var('findings') }}

Inspect and preserve valid partial work. Do not commit, push, modify the source plan, touch run
artifacts, change refs/remotes/Git configuration, or edit outside the issue paths — unless the
findings say the fix left something out of its declared paths, in which case edit the missing file
too, and the workflow widens the declaration to whatever this repair touched.

Return exactly one JSON object as the final response:

```json
{"status": "done|blocked", "notes": "what was repaired and what verification ran, or the blocker"}
```