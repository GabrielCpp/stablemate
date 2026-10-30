# The second agent

The three places a second agent that never reads the author's reasoning checks the study: the cards and framings of step 6, a decisive registration before it runs in step 7, and a decisive result before it counts in step 9. The steps themselves are in [`../SKILL.md`](../SKILL.md).

## Checking the cards and framings

Have the framings and the cards checked. A second agent that did not write them reads the
question, the premises, the framings and the cards, and nothing of the study's reasoning.
It answers both gates for each, names any assumption that makes the question unsolvable,
and names any two framings that share their input, output and role. A card or a framing it
fails goes back to repair. The rules for its counts, and for a rule that would return
every row, are under "The checker" in
[references/paper-gates.md](references/paper-gates.md).

A checker finding against a gate stays open until a repair answers it in writing or the
framing dies. A finding is a predicate the checker can run again, such as a line the code
must hold or a score an arm must not reach. The author's argument closes none. No decisive
run launches under a framing that carries an open gate finding, and none launches without
the design check of step 7. A run that would read the same fact the finding states is
apparatus for a known answer.

## Checking a decisive registration

A second agent that never reads the author's reasoning then writes a `design-check` row.
It reads `QUESTION.md`, the quoted clauses with their anchors, the code and the commands.
For each clause it says whether the anchored line does what the clause says, whether the
control is the strongest no-method one, and whether the method is the mechanism earlier
items credited. It designs a **cheat arm** for this instrument: the cheapest route from the
inputs to a passing score that uses none of the method, starting from the unchanged state
and a copy of whatever answers the prompt shows. It runs the cheat on every seed and writes
the scores into its row. A cheat that scores above the no-method control kills the
instrument before the run costs anything. It lists every route by which the answer could
reach the measured path without the method and tests each with a script over the generated
inputs. "Leaks" in [references/measurement.md](references/measurement.md) holds the rule.
Each finding is a predicate it can run again. A clause the run cannot meet, such as a
budget nobody can define, goes to the operator with the operator's words it reads, never
into an argument between author and checker.

The decisive command refuses to start until the registration names a `design-check` row
with no open finding. A script enforces that: the row exists, the clauses match
`QUESTION.md` byte for byte, every anchor resolves to a line and a row, the cheat scores
are recorded at or under the control, and the output directory keeps every reply for
regrading. The checker's judgment covers what a script cannot read: whether an anchored
line does what its clause says, which cheat to try, and whether a control is the strongest.

## Checking a decisive result

**Have a decisive result checked before it counts.** A second agent that did not write the
probe reads the row's `settles` sentence, the command and the bar, and nothing of the
study's reasoning. It re-runs the scorer on the retained replies, holds its number against
the bar, and repeats the leak check. A row whose replies were not retained is unchecked,
and a recount of success flags is not a regrade. Its number goes into the row's `checked`
field. When the two numbers differ, the row records both and the result stays open until
explained.
