export const meta = {
  name: 'okf-row-vet',
  description: 'Discover open/unowned plan rows and adversarially vet each against the goal (§1) and design (§4/§8)',
  phases: [
    { title: 'Scout', detail: 'find currently-open rows lacking a logged grounding citation' },
    { title: 'Vet', detail: 'three cold agents per row judge GROUNDED / PLAUSIBLE / UNGROUNDED' },
  ],
}

const GOAL_TEXT = `1. The goal in one sentence

The book is the product, described so completely and so truthfully that
running the description tests the product — and so that an agent holding
nothing but the book can operate the app and explain why it behaves as it
does.

Four properties, all at once:

- True. Every claim the book makes is one the product can be asked to
  demonstrate, and it is asked. The book earns its accuracy continuously by
  being executed, not by having been written carefully. A book that has drifted
  is loud, not quiet.
- Complete. There is nothing the product does that the book does not
  describe. Every screen, command and endpoint sits on a journey somebody can
  run. A capability the book cannot demonstrate is a hole in the book, not an
  exception to it.
- Sufficient. Reaching a screen, driving a control, bringing the stack up,
  pointing at an environment — all answered from the book. It replaces the
  source as the operational reference for everything except *how* the thing is
  implemented.
- Intelligible. The book carries business meaning derived from the code, and
  that meaning is reachable from whatever the reader is standing on. Stories
  link in as they are written; the concept holds the meaning now.

The acceptance test

Hand a Sonnet agent three things and nothing else — the book, the ostler
skills, and a driver MCP (Playwright, Maestro, a shell) — no source tree, no
prior knowledge of the product. It can:

1. bring the stack up and reach any screen,
2. drive any journey the book documents, end to end,
3. say what any part of the product is for, and which story asked for it,
4. and when the app disagrees with the book, report which one is wrong.`

const DESIGN_INDEX = `8. The settled tree — forty-eight decisions, in five groups.

What the book is (§1). True, complete, sufficient, intelligible — verified
by one acceptance test, run periodically, not by a gate.

How a flow becomes something that runs. D1 dispatch by (link target × runbook
driver); D9 mobile as a row not a backend; D19 one scenario per flow; D20 a flow
is atomic; D23 cross-surface flows hold a target set; D17 identity crosses
through a fixture; D24 vet per UI target; D18/D26 eight verbs in scope and six
deferred with named gap kinds; D4/D5 instances from fixtures, invalidity marked
positively.

How the book is held to its form. D2/D10/D11/D12 determined values before
prose; D3/D16 states as addressable nodes; D6/D13/D14/D15 environments derived
and guarded; D7/D25 scope asserted explicitly; D8/D27 exclusions declared.

How the book stays true. D31 verification is the flow running; D33 every
compile gap is a doctor code; D48 the citation digest decides book-vs-world;
D30 the walkthrough removed, because a scan produces prose and an execution
produces a verdict.

How the book stays whole. D39 everything reachable from an entry point,
verdict link-or-delete; D40 two graphs, two root sets; D41 entry points declared
in an entries node; D42 entry: seeds reachability and still demands coverage;
D43 runbooks reached, carrying requires:; D44 auto-deletion under three
conditions; D32/D47 coverage over six performable types; D45/D46 meaning split
by provability, position graded, prose not.

Order. D30 removal → Gate A (form checkable) → Gate B (audit works end to end)
→ builders restart → acceptance test.`

const SCOUT_AGENT_TYPE = 'general-purpose'
const VET_AGENT_TYPE = 'general-purpose'

const ROWS_SCHEMA = {
  type: 'object',
  properties: {
    rows: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          claim: { type: 'string' },
        },
        required: ['id', 'claim'],
      },
    },
  },
  required: ['rows'],
}

const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['GROUNDED', 'PLAUSIBLE', 'UNGROUNDED'] },
    dNumber: { type: 'string' },
    reason: { type: 'string' },
  },
  required: ['verdict', 'reason'],
}

function majorityVerdict(votes) {
  const rank = { UNGROUNDED: 0, PLAUSIBLE: 1, GROUNDED: 2 }
  const counts = {}
  for (const v of votes) counts[v.verdict] = (counts[v.verdict] || 0) + 1
  const total = votes.length
  const majority = Object.entries(counts).find(([, n]) => n > total / 2)
  if (majority) return majority[0]
  return votes.map(v => v.verdict).sort((a, b) => rank[a] - rank[b])[0]
}

phase('Scout')
const scouted = args && args.rows
  ? { rows: args.rows }
  : await agent(
      `Read /home/gabriel/Documents/workspace/stablemate/docs/plans/okf-executable-books.md, ` +
      `sections 2, 7 (Phases, and where we are) and any Follow-ups list. Find rows whose CURRENT ` +
      `status (not the row's original framing) is open and unowned — no worker/shepherd has closed ` +
      `it, and it does not already carry a logged D-number + §1-property citation for why it belongs ` +
      `in the plan. Verify each candidate's status directly in the file text, not from memory of the ` +
      `row's title. For each, return its row id and a one-sentence restatement of its claim as the ` +
      `plan states it — not your own paraphrase of why it might matter.`,
      { schema: ROWS_SCHEMA, agentType: SCOUT_AGENT_TYPE, phase: 'Scout', label: 'scout:rows' }
    )

log(`Scouted ${scouted.rows.length} open/unowned row(s): ${scouted.rows.map(r => r.id).join(', ')}`)

phase('Vet')
const results = await parallel(scouted.rows.map(row => () =>
  parallel(Array.from({ length: 3 }, () =>
    () => agent(
      `${GOAL_TEXT}\n\n${DESIGN_INDEX}\n\n` +
      `Candidate finding: "${row.claim}"\n\n` +
      `Judge this claim against ONLY the goal and design text above — you have no other context, ` +
      `no measurement trail, no diff. Answer GROUNDED (traces cleanly to one §1 property and one ` +
      `D-number), PLAUSIBLE (real gap, but the link to the goal/design is not fully stated), or ` +
      `UNGROUNDED (rests on an assumption the goal/design does not support). Default to UNGROUNDED ` +
      `if uncertain. Cite the exact D-number and §1 property, or name what's missing.`,
      { schema: VERDICT_SCHEMA, agentType: VET_AGENT_TYPE, phase: 'Vet', label: `vet:${row.id}` }
    )
  )).then(votes => {
    const cast = votes.filter(Boolean)
    return {
      id: row.id,
      claim: row.claim,
      verdict: majorityVerdict(cast),
      votes: cast,
    }
  })
))

log(`Vetted ${results.length} row(s): ` + results.map(r => `${r.id}=${r.verdict}`).join(', '))

return results
