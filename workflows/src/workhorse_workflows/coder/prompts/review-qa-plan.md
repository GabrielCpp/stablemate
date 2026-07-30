---
agent: agent
---

# Independently Review A QA Plan

Review the proposed QA plan before execution. Deterministic validation has already proved that
the YAML is structurally valid and names every known acceptance criterion and OKF obligation.
Your job is semantic: decide whether its actions and assertions can actually reach and observe
the behavior each `covers` claim promises.

## Inputs

- Story: `{{ workhorse_var('story_path') }}`
- Spec directory: `{{ workhorse_var('spec_dir') }}`
- Target environment: `{{ workhorse_var('target_env') }}`

Read the story, `qa-okf-context.json`, `qa-plan.yml`, `qa-plan.md`, review artifacts, and
`docs/qa/lessons.md` under the docs root (`docs_path` when non-empty) when present. Read applicable
QA skills and inspect cited native tests or flows when the plan delegates execution to them.

For every scenario, independently verify:

- its objective is explicit and corresponds to every AC/obligation in `covers`;
- causal preconditions are established and asserted rather than assumed from fixture selection;
- long browser/mobile chains begin at the documented flow entry and contain observable
  checkpoints before the terminal assertion;
- the terminal assertion proves the objective, not merely page presence or command success;
- expected error, retry, persistence, role, locale, keyboard, accessibility, and isolation paths
  from OKF are exercised where applicable;
- unexpected 5xx responses, crashes, and browser console errors cannot pass unnoticed;
- producer-consumer and pooled/shared-state obligations use an integration-strength oracle;
- each `verify:` reference has an appropriate level and actually runs in the declared environment;
- runner-owned artifacts will demonstrate the claimed result.

Do not execute the plan, drive the product, edit either plan file, or author evidence. This is an
independent review, not another planning pass. Approve only when the plan can meaningfully test its
objectives. Otherwise return precise revision notes keyed to scenario and coverage IDs.

Return JSON only:

```json
{
  "qa_plan_review": {
    "disposition": "approved",
    "notes": "Every objective has asserted preconditions, checkpoints, terminal proof, and runner-owned evidence."
  }
}
```

`disposition` is exactly `approved` or `revise`.
