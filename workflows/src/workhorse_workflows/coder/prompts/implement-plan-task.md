Implement exactly the worklist packet below against its immutable plan snapshot.

- Digest: `{{ workhorse_var('plan_digest') }}`
- Repository: `{{ workhorse_var('repo_root') }}`
- Packet: `{{ workhorse_var('task') }}`

```markdown
{{ workhorse_var('plan_text') }}
```

Read the plan, repository instructions, relevant existing code, and tests before editing. Inspect the
current worktree first: this state is resumable, so a prior attempt may have left correct partial
changes. Complete or repair those changes rather than starting over.

Change only paths owned by the packet. Meet every acceptance criterion, preserve compatibility
required by the plan, and run the packet's verification commands. Do not edit the source plan,
worklist, run artifacts, generated agent adapters, or `.git`. Do not commit or push; deterministic
workflow nodes own both operations and will reject out-of-scope changes.

Return this JSON object as the last thing in your response:

```json
{"status":"done|blocked","notes":"what changed and what you verified, or the exact blocker"}
```

`done` is a report, not the gate: the workflow independently checks changed paths and commands.