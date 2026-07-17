---
agent: agent
---

# Code-Reuse Check (Plan Stage)

You are running the **code-reuse** stage of the autonomous story workflow, immediately
after the plan was authored and before implementation begins. Your single job is to
catch the most common planning failure: **the plan proposes to build something that
already exists in the codebase** — a feature, endpoint, service method, component,
screen, hook, or utility — because the planner never searched for a prior
implementation. Catching it here means the implementer reuses what is there instead of
rebuilding (and diverging from) it.

You do **not** re-review the plan for correctness, scope, or style — implementation
review and QA do that. You look for **one thing**: existing code the plan should reuse.

## Inputs (authoritative — do not rediscover)

- Story path: `{{ workhorse_var('story_path') }}`
- Spec/artifact directory: `{{ workhorse_var('spec_dir') }}`

Analyze **only** the plan for the story above. If the story path is blank or missing,
report `status: ok` with a note that no plan was provided — do not pick a story
yourself.

## Steps

1. **Read the plan.** Read `plan.md` (and any service-specific `plan-*.md`) under the
   spec dir, plus the story it belongs to. If `plan-context.json` exists, read it to
   learn which repos/services the plan touches (`services[].repo` / `services[].path`).

2. **Extract what the plan intends to BUILD.** List the concrete units the plan says it
   will create from scratch: new endpoints/routes, service or repository methods,
   domain models, UI components/screens/widgets, state/providers, CLI commands,
   validators, formatters, and any "helper" / "util" the plan names or implies.

3. **Search the existing codebase for each one.** For every intended unit, search the
   affected repos (and shared/util packages) for an existing implementation of the same
   capability. Match on **behavior, not just name** — the existing version may be named
   differently. Prefer `rg`:

   ```bash
   rg -n "CreateProfile|UpdateProfile|profileForm|validateEmail" <repo>
   rg --files <repo>/pkg <repo>/internal <repo>/lib   # scan shared util/helper trees
   ```

   Look especially in shared utility/helper locations (e.g. `pkg/*`, `internal/*/util`,
   `lib/*/utils`, `packages/*`, a `shared`/`common` module) — reinvented utilities are
   the most common and lowest-risk-to-reuse finding.

4. **Judge each candidate.** A finding is real only when existing code genuinely
   provides the capability the plan would rebuild. If the plan already says it will
   reuse/extend the existing code, that is **not** a finding. When unsure whether two
   things are the same, err toward reporting it as advisory rather than dropping it.

## What is (and isn't) a finding

- **Finding:** the plan builds a new email validator; `pkg/validate/email.go` already
  has one. The plan builds a new "empty state" card; the design system already ships
  `<EmptyState>`. The plan adds a new `formatCurrency`; `lib/utils/money.ts` has it.
- **Not a finding:** the plan explicitly extends/calls the existing implementation; the
  existing code is in an unrelated layer and cannot be reused; the capability is
  genuinely new.

## Output

Return this JSON as your final response (the LAST thing you output). The workflow
captures it under `reuse_result`:

```json
{
  "reuse_result": {
    "status": "ok" | "needs_rework",
    "findings": [
      {
        "intended": "<what the plan proposes to build>",
        "existing": "<the existing code that already does it: repo, path, symbol>",
        "recommendation": "<how the plan should reuse/extend it instead>"
      }
    ],
    "summary": "<one sentence: what should be reused, or 'No re-implementation found.'>"
  }
}
```

- `ok` — the plan reuses existing code where it should; no re-implementation of an
  existing capability was found. `findings` is empty.
- `needs_rework` — the plan would rebuild at least one capability that already exists;
  each is listed in `findings` so the plan can be reworked to reuse it.

Do NOT modify the plan, source files, or anything else — this stage only reports.
