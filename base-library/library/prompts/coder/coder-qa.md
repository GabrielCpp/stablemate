---
description: "Prove a built story by scenario QA against its local stack: one scenario per criterion, a scored run, every failure classified, and a qa.md verdict. The coder qa subflow by hand. Product defects come back as findings, never fixes."
argument-hint: "<story-id>"
---

# Scenario QA for story $ARGUMENTS

This command does by hand what the coder `qa` subflow does in its owner turn
(`workhorse-coder run qa`). It covers what the books left: the criteria no book can state and the criteria no book
play observed. coder-book-qa sends a story here when no book covers it. You select the scenarios, run them, debug each failure
and record the result. QA never fixes the product. A defect in the story's code is a
finding you report.

Load {{ skill_link("ostler-cli") }} for `ostler env` and QA plans.
{{ find_by_tags("qa") }}

## 1. Select

Read the story, its acceptance criteria, `<spec>/plan.md` and `<spec>/review-answers.md`.
`ostler path spec $ARGUMENTS` names the spec folder. Read the repo's `AGENTS.md` and
`docs/qa/lessons.md` when it exists.

Then read the book of each service the story touches, before any code or test. Run
`ostler book search <noun>` for each noun a criterion names, `ostler book explain <module>
<Element>` for each screen, endpoint and journey it finds, `ostler book pages` and
`ostler book decisions <module> --story $ARGUMENTS`. The book says how to bring the stack up,
which account signs in, how a user reaches each screen and what each step shows. A scenario
walks the path the book gives, and its expected result comes from the criterion and the
book, never from the code under test. Read the code only for what the book does not hold,
and name each such gap in `qa.md`.

For each criterion, decide what observation shows it.
Each one takes the first proof that fits:

- **scenario**: a call, a screen, a command or a stored record on the local stack shows it.
- **integration test**: only a test can show it, because it needs concurrent writers, a
  restart, an injected failure, sustained load held to a threshold, or a dependency the
  stack cannot host. Write the test in the repo's own suite. Cover the criterion with a
  scenario that runs it through `qa.tool(<runner>).run(...)` and checks its result with
  `qa.verify(...)`. A red test is a product finding.
- **live check**: only a person working the environment the story is proved on can show
  it, and no scenario can drive it: a cloud permission, a routing rule between running
  services, a secret, a scheduled job, a migration on real data. Write
  `<spec>/manual-qa.md` in the form the `plan-qa` command gives, against that
  environment instead of DEV: a title naming the environment, `QA_DIR="<spec>/qa"` with
  `mkdir -p` per `ac<n>-<slug>/` folder, numbered `## 1) ...` steps that each save evidence
  under `$QA_DIR/ac<n>-<slug>/` and state a `Verdict:` rule, a cleanup section and a final
  `## Evidence manifest`, with no table and no script block. No scenario covers it. When
  every criterion is a live check, write no `qa_plan.py` and skip steps 2 and 3.

A criterion the local stack could show is never a live check.

Write `<spec>/qa_plan.py` by hand. Write one scenario per criterion that is not a live
check, or one for several that a single observation proves. Each scenario carries `covers=["ac:<n>"]` and a
`qa.check(..., covers=["ac:<n>"])` in its body. A criterion no scenario, test or live check can
show stops the story. Report it with the reason. Run `ostler qa lint` on the plan.

**Done when** every criterion is covered by a scenario or a live runbook, the plan lints,
and `manual-qa.md` holds every part of the form above for each live criterion.

## 2. Run

Bring the stack up with `ostler env up` for the services the story touches. Run the whole
plan, scored, from the spec folder, under a timeout:
`ostler qa run <spec>/qa_plan.py --spec <spec>`. The scored run is the verdict.

**Done when** a scored run is on disk.

## 3. Debug

Read `qa-report.md` and classify every failure:

- **product**: the code does not do what a criterion says, or fails where it ran before. A
  finding. Do not fix it.
- **plan**: the scenario asserts the wrong thing or reads the wrong field. Repair the
  scenario.
- **stack or setup**: the environment, a seed, a tool or a stale build. Repair it. When the
  cause is the repo's tracked code, such as its stack definition, it is a finding too.
- **evidence**: the proof is missing, stale or does not support its claim. Repair the
  scenario so it records it.
- **regression**: an existing spec this change broke, or a stale spec. Fix a stale spec
  against the real stack without weakening an assertion. A regression in the product is a
  finding.

Run one scenario alone with `--scenario <id> --out-dir <label>` while you debug it. Run the
whole plan again once a repair lands.

**Done when** the scored run passes, or every failure left is a product finding.

## 4. Judge the run

A passing status is not yet a proof. For each scenario, check:

- The causal precondition was established and asserted.
- The journey started at the flow's entry, not a deep link past the integration.
- The assertion proves the covered criterion, not page presence or command success.
- 5xx responses, crashes, console errors, partial writes and wrong producer data were
  ruled out.
- The cited evidence belongs to this run.

A criterion with universal language (`every`, `all`, `each`) needs each category checked.
One representative does not prove the rest. List a path before you call an artifact
absent.

**Done when** each criterion's verdict rests on evidence from this run.

## 5. Record

Create `qa.md` once with `timeout 30 ostler create spec $ARGUMENTS qa.md`, then write below
its frontmatter. Rewrite it on every pass.

```markdown
# QA: <story-name>

## Verdict
<status>, run <run id>, <date>. <one line of disposition>. The per-criterion report is qa-report.md.

## Assessment
<what the run proved, what it did not, and why>

## Owed on the environment
<each live check, the criterion it proves, the environment and the runbook path, or "none">

## History
- <date>: <status>: <outcome>
```

Never edit an evidence artifact, and never upgrade an `invalid`, `blocked` or `failed`
result. Commit the plan and `qa.md` by path with a `test` subject and the `Epic:` and
`Story:` trailers.

**Done when** `qa.md` is committed. Report `passed`, or each product finding with its
criterion, what you observed and the evidence path.
