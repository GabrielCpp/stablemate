---
agent: agent
---

# Adversarially Audit A Passed Ostler QA Run

The runner reported `passed` and the deterministic evidence gate validated its artifact
contract. Independently try to refute the pass from runner-owned evidence. Do not execute
the product again and do not author replacement evidence.

## Inputs

- Story: `{{ workhorse_var('story_path') }}`
- Spec directory: `{{ workhorse_var('spec_dir') }}`
- Gated status: `{{ workhorse_var('qa_status') }}`
- Gate notes: `{{ workhorse_var('qa_notes') }}`

Read all of:

- `qa-okf-context.json`;
- `qa-plan.yml`;
- `qa/qa-run.ndjson`;
- `qa/run-manifest.json`;
- `qa-evidence.json`;
- the story acceptance criteria; and
- every artifact you choose to rejudge from the current manifest.

Coverage is exhaustive and deterministic, not sampled. Confirm every required AC and OKF
obligation maps to an executed passing assertion in the ledger and current manifest.
After coverage is established, sample the riskiest evidence for qualitative refutation:
persistence/reload, event consumers, concurrency/idempotency, state isolation, journey
completion, visual state, recording continuity, and error handling.

Use machine-readable evidence for geometric/textual claims. Never invent fields or values
that do not exist in the ledger/artifacts. A runner pass is refuted when evidence shows a
real contradiction, a partial journey, or an assertion that does not prove its `covers`
claim.

An auditor may downgrade `passed` to `failed`. It may never upgrade a deterministic
`invalid`, `blocked`, or `failed` result. If any required context, plan, log, manifest, or
evidence is missing/malformed, the deterministic gate should have returned `invalid`; do
not manufacture a pass. Record that contract defect without treating it as product proof.

Append `## Independent Audit` to `<spec_dir>/qa.md`, naming the obligations and evidence
sampled plus any concrete refutation. Append below the existing content and leave the `---`
frontmatter block intact — it carries the `type:` that makes the doc an OKF Concept.

Return JSON only:

```json
{
  "qa_result": {
    "status": "passed",
    "notes": "Coverage was exhaustive and sampled evidence did not refute the runner pass."
  }
}
```

`status` is `passed` only when the pass stands; otherwise use `failed` with concrete
scenario, assertion, obligation, and artifact references.
