## Inputs (authoritative — do not rediscover)

- Story path: `{{ workhorse_var('story_path') }}`
- Spec artifact directory: `{{ workhorse_var('spec_dir') }}`
- QA notes: `{{ workhorse_var('qa_notes') }}`

## What to write

Read:

- `{{ workhorse_var('spec_dir') }}/qa-report.md` — the runner's per-AC account of the run:
  each criterion's verdict, the step every covering assertion ran in, its check, observed and
  expected values, and the screenshots and files behind it. This is where the per-AC content
  of the comment comes from; its assertion tables already hold the observed values, and an
  UNPROVEN criterion says why nothing looked at it
- `{{ workhorse_var('spec_dir') }}/qa-plan.md` — the runbook that was executed
- `{{ workhorse_var('spec_dir') }}/qa.md` — the assessment and audit of the run, when present
- `{{ workhorse_var('spec_dir') }}/qa-evidence.json` — captured evidence (if present)
- Any files under `{{ workhorse_var('qa_dir') }}` the report links — screenshots, assertion
  files, command output
- `{{ workhorse_var('story_path') }}` — to confirm the acceptance criteria

Produce one file: `{{ workhorse_var('qa_dir') }}/jira-comment.md`

The comment must be self-contained and copy-paste ready into Jira. Structure it as:
