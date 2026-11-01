# The study ledger

One JSON object per line, appended to `ledger.jsonl` in the loop's working directory,
`.study/<question-slug>/`. Append the row
when the step starts, with `end`, `actual_min` and `outcome` null. Rewrite that last line
when the step ends. Never delete a row.

```json
{"start": "2026-09-25T14:02:11-04:00", "end": "2026-09-25T14:31:40-04:00",
 "step": "write the 5 benchmark pages with the import bodies left out of the turn", "kind": "decisive",
 "settles": "under 60 s a page says turn context is the dominant cost",
 "estimate_min": 10, "actual_min": 29.5, "estimate_usd": 4, "usd": 6.2,
 "outcome": "5.9 min a page, down from 30; 1,000 pages is 98 hours against 8: still 12x off",
 "commit": "a1b2c3d"}
```

| field | holds |
| --- | --- |
| `start`, `end` | `date -Iseconds` output, taken when the step starts and ends |
| `step` | what was done, in one line |
| `id` | a short name other rows cite, such as `design-check` and `checked` do |
| `kind` | one of the values in the table below |
| `settles` | "A result of X on ⟨clause, quoted⟩ settles ⟨claim⟩", or null for exploration. It carries no comparison of the run to the bar. |
| `clauses` | for `decisive` only: each clause the run bears on, quoted byte for byte from `QUESTION.md`, with its `arm`, `code` (file and line) and `row` (the id of the row that measured it) |
| `gaps` | for `decisive` only: each clause the run does not meet, with the row that measured the gap's size. It is the only place a difference from the bar may be stated. |
| `design_check` | for `decisive` only: the id of the `design-check` row that cleared the registration. The command refuses to start while it is null. |
| `cheat` | for `design-check` only: the cheat arm in one line, its score per seed, and the no-method control's score beside it |
| `findings` | for `design-check` only: each as a predicate the checker can run again, with `open` or the row that closed it |
| `serves` | for `apparatus` only: the decisive step it makes runnable, or `the study` for setup every step needs, such as a snapshot commit |
| `ideal_path` | for `probe` only: the ceiling of the mechanism the probe serves, with the `ceiling` row it comes from, or `baseline` for an exempt row |
| `roof` | for `probe` only: the fastest the hardware or the task allows for the work the probe's stage does, with how it was computed |
| `trace` | for `probe` only: the row id or record of a paid run that answers the probe's question, or the sentence saying why none does |
| `terms` | for `ceiling` only: one entry per stage of the ideal path, each with its cost per unit, `measured` with its row or `assumed` with its source |
| `ceiling`, `bars`, `verdict` | for `ceiling` only: the sum of the terms, the cost bar and the outcome bar quoted, and `pass` or `miss` with the state line it set |
| `rung` | for `probe` only: `trace`, `turn`, `stage` or `system`, the rung of the instrument ladder it runs at |
| `blocked_by` | the operator's limit or the missing input that stops the row from running, when one does |
| `estimate_min` | wall minutes expected, written before the step starts |
| `estimate_usd`, `usd` | money expected, written before the step starts, and money spent, read from the host's usage record at `start` and `end`; null with a `usd_source` sentence when no record is reachable |
| `actual_min` | `end` minus `start` in minutes, computed from the two timestamps and never written by hand |
| `outcome` | the result, projected against the purpose |
| `commit` | the commit the step ran on, when it ran code |
| `checked` | for `decisive` only: the number the second agent recomputed, or null until it has |

The values of `kind`:

| kind | what it is |
| --- | --- |
| `decisive` | its result settles a claim about the purpose |
| `exploration` | it informs the field without settling anything: a profile, a reading of the records |
| `apparatus` | it makes a decisive step runnable, and names that step |
| `design-check` | a second agent's check of a decisive registration, written before its command runs |
| `probe` | a run that spends money or wall time; its row carries the gate's `ideal_path`, `roof` and `trace` fields before `start`, and a baseline says so in `ideal_path` |
| `ceiling` | the ceiling test of step 4: the ideal path's terms, each labelled measured or assumed, the sum, both bars, the verdict and the state line it set |
| `cause` | the converge state's diagnosis of one problem: its contrast, its why-chain, the construct named and its class, execution or design |
| `fix` | a change landed at a cause: the construct, what it became, the prediction, the commit and the probe row that reads it |
| `reflection` | a step back, written by the triggers in step 6 |

A study uses these kinds and no others, so two studies' ledgers read the same way.

A `reflection` row puts its three answers in `outcome`: where the time went, what is
settled, and whether the current path is still the cheapest.

A script reads the fields above before a decisive command runs: every `clauses` quote is a
substring of `QUESTION.md`, every `code` anchor is a line that exists at `commit`, every
`row` anchor is an earlier row's id, `design_check` names a `design-check` row whose
`findings` are all closed, and no `cheat` score exceeds its control. It also flags a
`settles`, `step` or `outcome` sentence that names the bar, a control, compute or a budget
and cites no row id. What the anchored line does, and whether the cheat was the right one,
only the checker can read.

## Reading it back

The ledger answers the efficiency questions without a model call:

- decisive results per wall hour, and budget spent per decisive result,
- the share of wall time per `kind`,
- every step whose `actual_min` or `usd` exceeded twice its estimate.

Compute them with a one-off `jq` or Python expression when writing the report.

## TRIED.md

One line per method or route, newest first:

```
| date | what was tried | result | why |
| --- | --- | --- | --- |
| 2026-09-25 | Teach the small agent each dependent's fix from the change that broke it | did not work | The strong model won 8 of 8 against 2 of 8 for the best baseline, but the gap was vocabulary, not cause |
```

- **what was tried** says the idea in plain words a reader outside the project follows,
  with no file names, function names or check ids,
- **result** is one of: worked, did not work, undecided, blocked,
- **why** is one sentence, and any number in it carries the number it was compared against.

A `blocked` line names the layer it stopped at, apparatus, mechanism or question, and the
cheapest change that would unblock it.
