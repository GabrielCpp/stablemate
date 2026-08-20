---
type: spec.qa
---

# QA Execution Assessment: expense-list

## Disposition

- **Runner status**: `passed` (`Ostler QA run returned passed.`)
- **Disposition**: `confirmed`
- **Failure class**: `none`
- **Objective reached**: `yes`
- **Scenarios**: `list-expenses-end-to-end` and `list-expenses-empty-and-missing-group`
- **Assertions**: 12 passed, 0 failed; see `qa/qa-run.ndjson` lines 25-40.

The run meaningfully exercised the story's intended live API objective. It started the declared
API daemon, passed the Firestore-backed readiness probe, created the group and members through
the real producer endpoints, recorded two expenses, listed them through the real consumer
endpoint, and completed both terminal branches.

## Checkpoint Review

### End-to-end listing

`list-expenses-end-to-end` began with `POST /groups`, then added Alice and Bob to the returned
group. Assertions `list-expenses-end-to-end-2` and `-3` established the causal precondition that
both member records carried the created `groupId`; membership was not inferred from setup order.
Assertions `-4` and `-5` confirmed the producer responses carried the submitted payer and amount.

The terminal list assertion `list-expenses-end-to-end-7` observed the complete two-item response,
including both payer IDs and amounts, and verified the returned IDs were `[Hotel, Lunch]` after
the expenses were created in `[Lunch, Hotel]` order. Assertion `-9` immediately re-queried the
same endpoint and compared the complete response, covering immediate visibility and persistence.

The runner-owned artifact `qa/steps/expense-list.json` contains the created group, members,
producer responses, listed collection, and reloaded collection. The corresponding assertion
artifacts are `qa/asserts/list-expenses-end-to-end-6.json`,
`qa/asserts/list-expenses-end-to-end-7.json`, and
`qa/asserts/list-expenses-end-to-end-9.json`.

### Empty and missing groups

`list-expenses-empty-and-missing-group` created a real group with no expenses and asserted the
exact empty JSON array at HTTP 200 in `qa/asserts/list-expenses-empty-and-missing-group-1.json`.
It then queried a never-created UUID and asserted a 404 plus a problem response whose detail was
`group not found` in `qa/asserts/list-expenses-empty-and-missing-group-2.json` and
`qa/asserts/list-expenses-empty-and-missing-group-3.json`.

The terminal artifacts are `qa/steps/empty-list.json` and `qa/steps/missing-group.json`. The
missing-group response is distinct from the empty response, so the run did not conflate an
unknown group with an existing group having no expenses.

## Coverage

| ID | Result | Executed proof |
| --- | --- | --- |
| `ac:1` | Pass | Complete two-item collection with payer IDs and amounts in `list-expenses-end-to-end-6` and `-7` |
| `ac:2` | Pass | Exact newest-first ID order in `list-expenses-end-to-end-7` |
| `ac:3` | Pass | Immediate full collection re-query equality in `list-expenses-end-to-end-9` |
| `ac:4` | Pass | Exact `[]` response in `list-expenses-empty-and-missing-group-1` |
| `ac:5` | Pass | 404 status and `group not found` problem body in `list-expenses-empty-and-missing-group-2` and `-3` |
| `ac:6` | Pass | Full live create-group → add-members → create-two-expenses → list journey in `list-expenses-end-to-end` |
| `okf:docs/features/api/http/api.md#tooling:contract` | Pass | Live group partition assertion in `list-expenses-end-to-end-8` and `qa/steps/expense-list.json` |
| `okf:docs/features/api/http/api.md:contract` | Context-only | Not owed: `required: false`, `evidenceRequired: context`; `qa-evidence.json` records no evidence for it by design |

`qa-evidence.json` records Pass for all six acceptance criteria and the required tooling
obligation. Its Fail entry for the umbrella API contract is not a failed story objective because
the context packet marks that obligation optional/context-only; it was correctly not claimed by
the plan.

## Integrity Notes

The `run-manifest.json` lists every assertion and scenario artifact under this run, including
`qa/qa-run.ndjson`, `qa/steps/expense-list.json`, `qa/steps/empty-list.json`, and
`qa/steps/missing-group.json`. The API daemon log at `qa/daemon-api-server.log` records the
created group, both members, and both expenses before normal runner shutdown. Both command-output
artifacts exist at `qa/steps/list-expenses-end-to-end-stdout.txt` and
`qa/steps/list-expenses-empty-and-missing-group-stdout.txt`; they are empty because these are
Python HTTP scenarios, not shell-output assertions.

The plan uses direct live HTTP calls and expected-status handling, so unexpected 5xx responses,
connection failures, malformed response JSON, or missing response fields would have interrupted
the scenario rather than producing a passing behavioral assertion. No UI, mobile, locale,
keyboard, auth, concurrency, or idempotency obligation appears in the story or required impact
packet, so no such journey was required or omitted from the objective.

## Independent Audit

- **Verdict**: `stands`
- **Refutation class**: `none`
- **Coverage map**: `ostler qa evidence-map` reported 1 `covered`, 0 `uncovered`, 0
  `claimed-but-unasserted`, and 0 `contradicted` obligations. The umbrella API contract is
  context-only (`required: false`) and correctly owes no evidence.
- **Acceptance criteria sampled**: `ac:1` through `ac:6` in the story. The end-to-end scenario
  starts with `POST /groups`, creates both members and both expenses, then reaches the list
  endpoint twice. `list-expenses-end-to-end-6.json`, `-7.json`, and `-9.json` show the complete
  two-item collection, newest-first payer/amount values, and equality on the immediate re-query.
  `empty-list.json` and `list-expenses-empty-and-missing-group-1.json` show an existing group's
  exact empty array. `missing-group.json` and
  `list-expenses-empty-and-missing-group-2.json`/`-3.json` show a distinct 404 problem response
  with `detail: "group not found"`.
- **Continuity and error review**: `qa/qa-run.ndjson` records both live scenarios as passed with
  12 passing and 0 failing assertions. The daemon log records the producer operations and no
  5xx or crash during the scenarios; the later shutdown signal is outside the journey. The
  manifest contains no screenshots, layout digests, or vet reports, and this backend story has
  no visual obligation to require them.
- **Qualitative review**: The evidence uses the declared live API target rather than mocks or a
  deep link, preserves the created group identity through members, expenses, and listed items,
  and keeps empty and missing-group state isolated. No evidence demonstrates a contradiction,
  partial acceptance-criterion clause, stale artifact, or unsupported coverage claim.
