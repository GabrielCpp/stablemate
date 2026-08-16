Repair the current implementation of the worklist packet. Do not broaden its scope.

- Digest: `{{ workhorse_var('plan_digest') }}`
- Repository: `{{ workhorse_var('repo_root') }}`
- Packet: `{{ workhorse_var('task') }}`
- Repair pass: `{{ workhorse_var('repair') }}`
- Deterministic findings:

```text
{{ workhorse_var('findings') }}
```

Immutable plan content:

```markdown
{{ workhorse_var('plan_text') }}
```

Read the existing changes and the full command output, fix the root cause within the packet's owned
paths, and rerun its verification. If the findings say the packet left something out of its declared
paths, edit the missing file too — the packet's declaration is what the finding is about, and the
workflow widens it to whatever this repair touched. That is the one reason to write outside the
declared paths; anything else is broadening the scope. Do not edit the plan, worklist, run
artifacts, generated agent adapters, or `.git`. Do not commit or push; the workflow owns
publication.

Return this JSON object as the last thing in your response:

```json
{"status":"done|blocked","notes":"what was repaired and verified, or the exact blocker"}
```