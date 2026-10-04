# Building the framings

The full rules for the four moves of step 5 in [`research-study`](../SKILL.md), and for
the brief every framing agent receives. The skill carries each move in short. This file
carries what each move must return and how a return is judged.

## What makes framings differ

A framing
that learns does name whose work supplies its training data: the target's own past,
other sources of the same kind, data generated from a known structure, or a stronger
system working on the target. Gate 2 counts
that data. When no framing may choose the source, every row takes the obvious one by
default, and the gate fails them together.

Write at least three framings. Isolation keeps a framing from inheriting another's details,
and it does not make framings differ. Agents that share a model and read the same documents
converge on one reading. Handing a later agent the first reading and one axis to vary does
not fix that either: the agent turns that axis and copies the first reading on every other
one, so every framing is a sibling of the first. Framings differ when each is built from
its own choice on every open axis. Axes drawn from the question's own words still share
one vocabulary, so every value on them varies one literal reading.

## The four moves

1. **Restate the question by analogy.** At least three agents each restate the question
   in the terms of one distant field, such as a type system, the geometry of a space, a
   research line that met the same problem, or, for a question about learning, what the
   learned space must hold rather than the arithmetic that fills it. The study picks the
   fields. A field the operator named is a seed, not the list. At least half the fields
   are the study's own, and each sits far from the question's domain, from the operator's
   examples and from the other fields: a physical or life science, a craft with its own
   practice, a theory of communication or of decisions. Each agent reads the
   question and the premises, and no other restatement. Each maps the question's parts
   onto its field's objects, and names what that field already knows about the problem:
   what it holds solvable, what it holds impossible, and what it would measure. A
   restatement says what, never how. Each one returns the axes and the values it adds
   that the literal reading lacks. One that adds none is a synonym, and it is replaced.
   A restatement without a decomposition is a metaphor, and no framing can be built on
   it. Each one breaks the problem into the parts its field would cut it into. For each
   part it names the matching part of the real problem and works one case from a sample
   of the operator's real work through it. It then states what share of that sample the
   part covers, and which cases it leaves to another part. It ends with where to start:
   the part whose check is cheapest and whose failure would change the most.
2. **List the axes.** One agent reads the question, the premises from step 2 and the
   restatements, and nothing else. It lays the decompositions side by side. A part one
   field names and another misses is an axis. It lists the axes a reading must choose on: the role the thing under
   study plays, the input it reads when it runs, the output it produces, what counts as
   right and who judges, what the question's key verb is measured against, which part of
   the problem the study may redesign, whose work supplies the training data, and any axis
   the question adds. Every check gate 2 makes turns on some axis, and that axis is listed. For each axis it
   writes **fixed**, with the operator's words that fix it, or **open**, with at least
   three values. An axis is fixed only as far as its words go. "Reduce my dependency"
   fixes a direction, not zero, and "prefer" fixes a preference, not a requirement. A
   fixed axis stated stronger than its quote removes readings the operator left open,
   and nothing downstream sees them go. A value says what, never how. A value that names
   an algorithm, an architecture, an algebra, a fitting method or a data generator is a
   candidate, and it waits for step "Then the candidates". The source of the training
   data is a what, and a generator that draws pairs from that source is a how. Rows built from mechanisms
   differ in implementation and share one reading of the question. At least one value
   per open axis is one the project's existing apparatus does not support. It then holds every open value against every fixed axis and drops a
   value that breaks one, with the quote that breaks it. A test that drops one value runs
   on every value of that axis. A value that falls back to a weaker judge, input or source
   on some cases inherits every defect of that fallback.
3. **Draw the rows.** Pick one value per open axis for each framing, so that any two
   framings differ on at least half of the open axes. No row is the "direct" reading, and
   no row is written first for the others to vary. Each clause of the question is the
   measure a verdict rests on in at least one row. A clause such as "at low
   cost" that no row is judged by is a reading the field never tests. Each clause's
   measure passes step 2's proxy test before any row is drawn. A measure that reads zero
   or a constant for some part of a named lever, whatever the method does, is a proxy.
   A share of cases a prior admits is a proxy when the prior always admits a move that
   covers any output. The rank of a right output, found by judging candidates in order, is
   a pass rate at k, and every rule for an untrained pass rate governs it. A comparison
   whose reference arm may read zero names the anchor that stops it, and no row drops
   that anchor. Before rows are drawn, a verdict that matches against a reference arm is
   tested against this rule over the range the row predicts for that arm. A verdict
   that reads a share of the gap between two reference arms passes the proxy test only
   when the predicted ranges of the two arms cannot meet. Otherwise the row states the
   smallest gap it reads and how it reads a gap at or below it. A probability or a rank a prior gives the one recorded answer credits only
   that answer. It passes the proxy test only when a different right answer cannot score
   worse, or when the verdict rests on a judged output. A judged output reported beside a
   verdict that does not rest on it does not count. A control that draws its
   alternatives from within a stratum reports how many cases stand alone in their stratum.
   A case alone in its stratum makes the control equal the method by construction.
4. **Write each row in isolation.** A fresh agent, or a fresh context, gets the question,
   the premises word for word, pointers into the project and its row. It reads nothing the
   study has produced and no other row's framing. It writes the framing its row implies. A
   row agent never repairs its own row. When a value fails gate 1, the agent stops and
   returns that value with the operator's words that break it. When a value makes the
   framing fail gate 2, the agent returns that value with the check it fails, such as a
   measure that reads zero before any training. A row agent never rules its own defect
   harmless. An argument that a defect affects every arm alike, or that a direction still
   holds if an assumption fails, rules it harmless. It passes only when the defect's rate
   is measured and reported. A pass with conditions is a repair, and the value goes back. A row states
   each bound under which its pass holds as a break-even: the value of the rate at which
   the verdict stops holding. A break-even inside the range the record or the price list
   allows for that rate returns the row. A break-even outside that whole range returns
   nothing. It becomes the kill result of the first timed unit that reads the rate, and
   the schedule runs that unit before the spending it guards. A rate one timed unit on
   things that exist today can read is read in step 4, and it returns no row. A rule that
   returns every row with an unbuilt part makes the question unsolvable by construction.
   The row computes each break-even itself, with a script it names and hashes, by one
   stated method. A break-even the row did not compute is no break-even, whether another
   row, the axis list or the brief supplied it. Two phases that overlap in time on one
   machine count once only when the measured load of each is stated. Otherwise they are
   priced in series. Every unread rate a pass depends on carries a break-even, whether or
   not the record gives it a range. A rate with no range is read at its first timed unit,
   before the spending it guards. A heading
   that claims no return does not override a break-even inside the range.
   A rate the verdict itself reads is no condition. A rate that decides whether the
   verdict can be read at all, such as a run time, a writer's pace or a judge's error
   rate, is a condition unless the card shows the check passes across the whole range the
   record allows for it. The card states that range and its source. A rate step 4 could
   measure is measured there, and the card cites the measure instead of a range. A return claims
   the value cannot work, and it carries the same burden as a pass. Before returning, the
   agent names the obstacle and asks whether it is real: whether a premise or another
   value of the row already handles it with no value changed. A part the operator
   assigned to another component is handled by that component. An obstacle
   the premises already handle is no failure, and the value stays. A checker holds each
   return to the same test. Agents that share a model
   and repair alone reach the same repair, so five repaired rows converge on one yardstick.
   The axis agent drops or corrects the value for every row, redraws the rows, and the
   failed rows are written again. Before any row receives a value, the axis agent tests
   the value's own text against every gate 2 check, and fixes or withdraws a value that
   breaks one. The axis agent also checks each brief clause that names a rate, a range or a
   rung against the price list before rows run, and two clauses that disagree are a brief
   fault. A value the brief states and the row omits is a row fault, and the row goes
   back. Every total the axis list states equals the sum of the parts it lists, and
   the checker recounts each total before tabling rows against it. A schedule rule that
   leaves an assigned component with no input is a narrowing, and the axis list reconciles
   the two before rows receive them.

Four rules hold for every framing agent:

- an agent that cannot read the whole skill stops and says so. Its gate section answers
  every check by name, with a reason for any check it finds not applicable,
- the brief carries the question, the premises word for word, pointers into the project
  and the agent's row. It also lists each fixed axis with the operator's words that fix it
  and the sampled cases it caps, so the row subtracts them before it states a ceiling. It
  carries, in full, the axis list's statement of what no value removes, and the identity of
  every sampled case the list counts in a class. A brief that points at a document the row
  does not receive is a brief fault. It
  states each assigned value in the axis list's full text. Before judging a return, the
  checker compares the brief's wording to the list. A return caused by a clause the brief
  dropped goes back to the briefer, and the value stands. The brief
  carries nothing the briefer concluded. A sentence such as "the
  task here means X" in a brief is the briefer's framing, and every agent that reads it
  inherits it. A premise the briefer paraphrased is the briefer's framing too. The
  brief quotes in full every decision and clause that asks each row to report a figure,
  never in paraphrase, and ends with them as a checklist. The row answers each item by
  name. The checker ticks each row against the decisions themselves, not against the
  brief's list,
- anything the loop or its agents made earlier counts as study output: a roadmap line, a
  hypothesis, a result, and also code, a benchmark, a judge or a testbed. A framing agent
  reads study output for facts it can check, never for goals, bars or verdicts. An artifact
  the study built is one value on an axis, never the default,
- on a refill after a study ends, the framing agents also read the one-line status of each
  past framing in `FRAMINGS.md`, so they can avoid it. They read none of its
  implementation, because a dead framing's details are the main route of contamination.
