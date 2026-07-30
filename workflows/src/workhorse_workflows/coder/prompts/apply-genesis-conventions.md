# Apply repository conventions to the new service

A new repository has just been created at `{{ workhorse_var('target_dir') }}`. Git is
initialised, `agents.yml` is written, farrier has installed the packs and rendered the
scaffolds, and the stack's native init tooling has produced a working skeleton at
`{{ workhorse_var('service_root') or '.' }}`.

Your job is the part that is genuinely judgement, not mechanism: make this repo look like a
repo someone would want to work in, using the conventions of **its stack** as the skills you
have been given define them.

## What you are working from

- The service skeleton at `{{ workhorse_var('service_root') or '.' }}`, exactly as the native
  tool generated it — do not fight its layout, extend it.
- The skills installed for this stack. They are the source of truth for what "conventional"
  means here. Follow them; do not substitute your own preferences for a stack you happen to
  know well.
- `agents.yml`, which declares `workspace.service_roots` and `workspace.service_markers`.

## What to do

1. **A `lint` target.** Add a `Makefile` at the repo root with a `lint` target that runs the
   stack's real linter (whatever the skills specify — not a placeholder, not `true`). The
   coder workflow's lint gate degrades to a *skip* when no such target exists, so a missing
   one does not fail loudly, it just stops checking anything. That silence is the problem.

2. **A `test` target**, alongside it, running the stack's test runner — even if there are no
   tests yet. The first story to add one should not also have to invent how tests are run.

3. **Layout the skills call for.** If the skills define a package/folder convention the native
   tool does not generate on its own (handler/service/repository layering, a routes directory,
   a lib split), create the directories and any minimal placeholder the convention requires.
   Keep it to structure. Do not invent product code — there are no stories yet, and anything
   you write now is scope nobody asked for.

4. **A `.gitignore` that is actually complete** for this stack, merging with whatever the
   scaffold already seeded rather than replacing it.

## What not to do

- **Do not create the skeleton yourself.** You are extending one the stack's own init tool
  already produced. If `{{ workhorse_var('service_root') or '.' }}` looks empty or lacks its
  marker file, the init step failed — say so and return `"blocked"`. Do **not** hand-write a
  plausible-looking tree to fill the gap. This has happened: an agent handed an empty `web/`
  invented `routes.ts` and `.gitkeep` stubs, producing something that read as a service but
  was not one, and the real `npm create react-router` never ran. A skeleton nobody generated
  is worse than no skeleton, because every later stage trusts it.
- **Do not implement any feature.** The backlog has not been authored into stories yet. A
  service skeleton plus conventions is the whole deliverable.
- **Do not add a git remote or push.** This repo is local-only by design; PR delivery is
  optional downstream.
- **Do not edit `agents.yml`'s `workspace:` block.** The validator checks the service against
  what that block declares — editing it to match a layout you changed would make the check
  agree with you rather than verify you.
- **Do not create `docs/` content.** The scaffolds own that tree.

## Output

Return this exact JSON in your **final response**:

```json
{
  "conventions_result": {
    "status": "applied" | "blocked",
    "notes": "What you added and which skill/convention each thing came from. If blocked: exactly what was missing or contradictory, and what you would need to proceed."
  }
}
```

Use `"blocked"` when the installed skills do not say enough to establish a convention for this
stack — guessing produces a repo whose conventions nobody can point at a source for, and every
later story inherits that. Being blocked here is cheap; being wrong here is not.
