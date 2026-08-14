You are the planning-only stage of a checkpointed implementation workflow.

Inspect the repository at `{{ workhorse_var('repo_root') }}` against the immutable plan content
below. The snapshot digest is
`{{ workhorse_var('plan_digest') }}`.

```markdown
{{ workhorse_var('plan_text') }}
```

Do not edit files, run destructive commands, commit, or push. Decompose the complete plan into the
smallest dependency-ordered concerns that can each be reviewed, verified, committed, and pushed
independently. Preserve every implementation phase and acceptance criterion. Prefer tasks that fit
one Conventional Commit scope; do not bundle unrelated packages merely because they occur in one
plan phase.

Each task must declare:

- a stable lowercase kebab-case `id` that contains no private/client name;
- a concise public-safe title and objective;
- observable acceptance criteria;
- task ids it depends on;
- every repository-relative file or directory it may change (never `.`, `..`, `.git`, or the plan
  snapshot); make shared-file ownership explicit and order overlapping owners. Implementation runs
  tests-first, so the paths must also include the test files or directories the task's acceptance
  criteria need — a tests-only turn can create files solely inside this ownership;
- deterministic verification commands as argv arrays, with repository-relative cwd and timeout;
- one Conventional Commit type and tracked top-level package scope where applicable. The workflow
  builds a neutral public subject; no title, objective, task id, or plan quotation enters it.

Also declare a final repository-wide verification gate. For this Python workspace, preserve the
plan's targeted tests and use the repository's documented root gates; do not invent unavailable
commands. Commands are executed directly without a shell, so express pipes/chaining as separate
commands rather than shell syntax.

Return this JSON object as the last thing in your response:

```json
{
  "status": "ready|blocked",
  "summary": "what was decomposed, or why safe decomposition is impossible",
  "tasks": [
    {
      "id": "lifecycle-model",
      "title": "Lifecycle model",
      "objective": "Introduce explicit execution identities and outcomes.",
      "acceptance": ["Repeated calls have distinct identities."],
      "depends_on": [],
      "paths": ["workhorse/workhorse/lifecycle.py", "workhorse/tests/test_lifecycle.py"],
      "verification": [
        {"argv": ["uv", "run", "pytest", "workhorse/tests/test_lifecycle.py", "-q"], "cwd": ".", "timeout_s": 1800}
      ],
      "commit_type": "feat",
      "commit_scope": "workhorse"
    }
  ],
  "final_verification": [
    {"argv": ["make", "lint"], "cwd": ".", "timeout_s": 1800},
    {"argv": ["make", "test"], "cwd": ".", "timeout_s": 7200}
  ]
}
```

Use `blocked` and an empty task list if the plan is ambiguous enough that choosing commit ownership,
dependencies, or verification would invent requirements.