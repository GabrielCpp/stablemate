# Score one backlog bullet against the repo that was built

You are grading a repository that an automated agent workflow produced from a backlog of
user-observable behaviors. You are grading **one** of those bullets. Be a hard marker:
this score exists to detect a workflow that produces plausible-looking output, so
"it looks like someone was working on it" is not a passing signal.

## The bullet

    [{{bullet_id}}] {{bullet_text}}

## What the repo's own planning documents claim about it

- Repository root: `{{target}}` (this is your working directory)
- Epic(s) whose `## Backlog bullets covered` list names this bullet: {{epics}}
- Stories under those epics, with the status each records:

{{stories}}

Treat all of the above as **claims, not evidence**. An epic listing a bullet means the
planner intended to cover it. A story marked "QA passed" means the workflow believed it
finished. Neither is proof that working code exists — verifying that is your job, and a
gap between what the documents claim and what the code does is exactly what this
benchmark is built to find.

## The rubric

Assign exactly one level:

{{levels}}

Rules for choosing:

- **Read the actual code before scoring above 1.** Open the files. A story marked done
  with no implementing code behind it is level 1, not level 2.
- **"Every surface the bullet implies"** — work out which surfaces this bullet needs from
  the bullet's own wording and the epic's scope table. A bullet that says "on a phone"
  needs the mobile app. A bullet that names no surface needs *both* the web and mobile
  front ends plus whatever API work it implies. If one required surface is missing or is
  a placeholder, the bullet is level 1, not level 2 — partial credit across surfaces is
  not available, because a feature that exists on one of two front ends does not satisfy
  a person who uses the other.
- **A stub, a TODO, a hard-coded fixture, a scaffold left as generated, or a handler that
  returns a canned value is not an implementation.** Level 1.
- **Level 3 needs executable evidence** — a test, a QA artifact, a recorded assertion —
  that exercises *this* behavior. Code that merely looks correct is level 2. A test file
  that exists but asserts nothing about this bullet is level 2.
- When you are torn between two levels, pick the **lower** one.

## Evidence you must cite

Every level of 2 or 3 requires at least one `evidence` entry, and each entry must be a
**real, repo-relative path** — optionally with a symbol or line after a colon, e.g.
`api/internal/todo/service.go:CreateTodo` or `web/app/routes/signup.tsx`.

Your citations are checked against the filesystem. Any bullet whose cited paths do not
resolve is automatically capped at level 1 and reported as unproven, so a guessed path
costs you the whole score for this bullet. Cite only paths you actually opened.

## Respond with

A single JSON object and nothing else:

```json
{
  "level": 2,
  "evidence": ["api/internal/todo/service.go:CreateTodo", "web/app/routes/todos.tsx"],
  "reason": "one sentence, under 25 words, naming what you found or what was missing"
}
```
