# The paper gates

The full rules for step 6 in [`research-study`](../SKILL.md): what the card states, two
checks of gate 1, every check of gate 2, and the agent that checks the cards. The skill
states each check in short. A section here holds the cases where that check passes wrongly.

## The card

- **the question's task**: its input, its output and the role it gives the thing under
study, copied from the operator's words and not paraphrased,
- **the method's task**: the input the method reads at test time, the output it produces,
and who or what produces each part of it, once under test and once in use,
- **the training task**, when the method learns: the input, the target, where the pairs
come from and how many exist,
- **the judge**: what counts as a right output,
- **every assumption** the method needs, one per line, each marked as stated by the
operator, checked, or assumed,
- **which inputs are fixed and which are designed**: an input the world hands over, such
as an existing system, is fixed. An input whose format the study may choose, such as
the notation a request is written in, is designed. An input the study wrote, such as
its own sample requests, is designed even when it already exists. Mark each, and cite
the premise that makes it so,
- **the named method's defining parts**, when the candidate borrows a name such as an
architecture, an algorithm or a published technique: each part that makes the name true,
marked built or left out.

## The role matches

A check of gate 1.

A question that asks how to use a component is not answered
by casting that component as a replacement for the whole system. Write the role the
question gives it on the card. When the done-condition names what the component must
author, the card names the part of the output that component writes in the method, and
the part every other component writes. A component the method only consults, such as a
lookup, a ranker or a hint another system may ignore, authors no part of the output.
The card then answers a question about the other components, and fails this gate. When
a plain mechanism with no training could serve the same consultation, the card reads
that mechanism first, because the trained component can at best tie it.

## The input exists in use

A check of gate 1.

Trace one request from the operator's hands to the method's
input, as it would run after the study ends, and name the producer of every designed input
there. When the operator's words place the input in a form and leave its writing outside
the question, its writer in use is the operator's own process, and the method is not
charged for it. Otherwise the producer in use must be the one the test set used. When the
study's own session writes the test inputs and nothing named writes them in use, the test
measures a pipeline nobody will run. Write the producer in use and its cost per request on
the card, with the operator's words that place it.

## Identifiability

The input carries the information the output needs. For each part
of the output, name the part of the input it comes from. A part with no source must be
guessed, and the guess rate is the ceiling. A part the output carries through without reading
it needs only what the method decides from: its kind, and which instance it is, so a
repeat stays the same instance. Its content can be restored after. Only the parts the
method decides need a source it can read. A source counts only when the card names its
route into the method's input and the input still fits, at the size and price the card
states, beside everything else it holds. A source the card lists as available, with no
route or no room, is no source. Check the training pairs and each test set the
verdict reads, one at a time. A test set on which a decided part has no source fails,
whatever the other sets show. A guess rate is a ceiling, never a source. The check
covers every stream that changes the method's state during the run, such as per-case
updates or a growing memory, and not only its training pairs. Each stream feeds a case
only material that existed before that case and that the case could have seen. An
earlier case's output that names a later case is a leak through that stream. When the missing part sits in a designed input, the repair is to
change the input's format so it carries the part. Accepting the loss is a choice the card
must argue for, and a designed input never loses a fact by default.
A test input written after its answer existed may leak it, and one written from the
answer does. Run-time inputs are written before the answer, so every measure reports
apart on the test cases written that way, even when they are few. A value that reads the
live environment at run time needs the same reads in every training pair and every
historical test case. A historical case replayed against today's environment reads the
state after the change, and that is a leak. A writer who fills a designed test input
from linked material reads that material as it stood before the answer existed, and the
card names the version it reads. A writer of training inputs reads no state in which a
held-out request or its material is already visible. A split never puts two cases that
share one answer on opposite sides. The axis list counts both before any row receives
the split, and a screen that reads held-out answers while training data is made is a
leak, not a repair. The card states whether a component that builds from the project at
test time, per case, counts as a writer of inputs under this rule.

## Train equals test

The training task has the same input and the same output as the
measured task. A model trained to edit one artifact into another is not trained to write
the second from a description. When the input form is designed, each training source
names who writes that form for each pair, and counts it. A source with no such writer
fails.

## The judge accepts every right answer

A judge that credits only one reference
output fails a correct output that differs from it. Prefer a functional judge, such as
compiled checks, tests or a build. When the judge must compare against a reference, say
how many right answers it accepts and why that is enough. A recorded past output counts
as a right answer only after the judge accepts it, and the card reports how many
recorded outputs the judge rejects. A judge that rejects most of the operator's own
accepted outputs is read before any row rests on it. The card says whether the fault
is in the reference, such as work bundled beyond the case, or in the judge, and cites
the operator's words for the bar it holds. A judge whose verdict comes from a model
call gives one sample per call. Its flip share on one output across repeated calls is
read before its verdicts count, and a margin inside that share is no reading. A case where a measure lacks its second right answer
reads as unmeasured, never as a score on the recorded output alone. A judge shown a second output
beside the one it grades says whether it grades each alone or picks between them. One
that picks between them compares against a reference, and the same count applies.

## The judge rejects wrong answers

Name a wrong output the judge would pass, such as
an output that passes checks the method wrote for itself. A judge that passes it credits
the method for grading itself. The first wrong output to try is the unchanged state. A judge that runs checks at a
past state reads them before the change first. A check counts against the change only
when it passes before the change and fails after it. A check that defines success
counts for the change only when it fails before and passes after. A judge that reads a
check already failing before the change as a rejection rejects every output at that
state, the unchanged one included. A count of recorded outputs marked failed reads each
record whole, its title and its body, and counts a mark only when it names that
record's own case. Every clause that counts failed cases uses that count, and a wider
count is reported apart under its own name. A recorded output enters a set of known wrong outputs only after a later record names what
was wrong with it. A status label alone does not qualify. Read each member, and count the
ones whose label named something else. A
judge built from the input the method reads cannot check a fact that another value
forbids that input to carry. List each class of value the method reads from outside the
request, and name beside it the check or record that fails a wrong value. A sentence
saying each class has a check is not the list. The judge sees the logged
source of every such value, or that class is unjudged and the check fails. The second
wrong output to try does what was asked and
also something that was not asked. A judge with no reader of the request shows how it
rejects that output. A case the judge cannot score stays in the denominator as a
failure, and the count of such cases reports beside the rate. A part of an answer that a
tool generates and the judge reads needs a stated author before the ceiling counts that
case. Regenerating it from the output under test makes the check vacuous.

## Method fidelity

Every defining part of the named method is built, or the verdict
names the gap. A result from a method missing its defining parts is a result about
another method, and it cannot close the named one.

## The data fits the target

The training data comes from the distribution the test
draws from, in kind and in volume. Name the source and count it before building. A
source counted as unbounded is also counted in kind: the share of real test cases whose
shape it can produce. A count taken from a published description is not a count of data
on hand. When a training input is rendered from a source, count the source items that
carry the facts the test input carries. An item that carries only a one-line label
leaves the rest to be guessed. When the source was written after its answer, count it
both ways: items missing facts the test input carries, and items stating facts of the
answer that no test input carries. Length is not a count of facts. Read a sample and
state the share. A source that writes both the request and the answer counts in kind by
the share of test shapes it can produce at the state it writes against. A shape that
needs a defect or an event to exist first counts only where one exists, and the card
counts where. State how many test cases exist today, the rate at which new ones arrive,
and the date the set reaches the resolution floor, and price the wait. A set that starts
empty and grows only if someone changes how they work states that change as an
assumption, with its current rate. A verdict whose floor date falls after the study's
date returns the value that sets the test form. The study's date and every pace it
sets for itself are values too, and the same checks apply to them. A date or a pace
under which no framing reads its verdict by its cheapest path makes the question
unsolvable by construction. Re-derive it once, before any row runs, from the operator's
words and the operator's record, never from what a row needs, and record both versions.
A floor date uses the rate the record shows for whoever writes the test input, counted
in the units that writer produces. It never uses the rate of outputs from a system that
writer directs. When several rows draw on one writer, split the rate among them first. A
rate above the writer's record is a condition, and the value that needs it returns.
Before returning it, read the operator's words for who may write that input. A writer
the operator named, the study included, is a source, and its rate is what that writer
can produce. A form of input the operator's words call for is part of the question,
never a smaller question. A writer of training inputs is priced the same way: at its
record, in the units that carry the volume this check needs. A pace and a volume that
disagree are a contradiction.

## The compute fits the claim

Estimate what the method needs to learn the task at all,
from the size of the output space and from published results. A budget short by orders
of magnitude makes the run measure the budget. This check is the exception to the gate's
rule: it never assumes the uncertain part goes the method's way. When the estimate from
published results exceeds the budget by an order of magnitude or more, the check fails
unless the budget is resized or the verdict states that it measures that budget. Price it on the hardware the run will
use, checked on the machine and named on the card. Price memory as well as time: the
largest input one step holds, at the precision the device supports, against device
memory. Price generation at the bound that limits it, memory traffic or arithmetic, and
name which. A price per output is computed over distinct outputs. When several cases
share one output, a per-case mean understates the output's size. Every sub-check the
judge runs carries a per-run time in the run price, and a sub-check with no recorded
time is a deciding rate. For each such sub-check the row states one of two things: the
bound it is priced at with its break-even, or that it returns as a condition. Assuming zero, leaving it out
and staying silent are not allowed. Name whether the software stack supports the device. When that support is
unconfirmed, price the time on the fallback device too. Every hour spent building a
component the prior or the method needs counts in the cost the verdict reads, and a
component that does not exist yet is priced before the verdict is read. Every
reference arm a verdict reads has a builder, an input and a price in the build list. A
definition alone is no arm. Price build work
at the pace the operator's own record shows for that kind of work, and name the builder.
A pace taken from a builder the operator does not use is an assumption, and it is stated
as one. When the build and a test source draw on one limited resource, such as people,
sessions or machines, price them together, and move the floor date by the time the
build holds it. A budget in machine days counts from the time the row's inputs are
ready, not from the study's start. A row whose verdict lands after the study's date
fails the date check even when its machine days fit. Under a serial schedule the row
states whether the next case may start while the current one waits on a step that uses
no local machine time. If it may not, the row prices that wait on the calendar. A budget the operator's words fix, such as a named machine, is never a
reason to call the question unanswerable. When the estimate exceeds that budget, the
verdict reads the lever at several budgets up to it, and states the smallest budget at
which the oracle control separates from the random one, or that none does. When per-case updates run inside every arm, each
budget rung reads as the rung plus that stream. A rung smaller than the stream is no
distinct rung, and the smallest-budget reading moves to the first rung that exceeds it. A row never
narrows a clause measure's cost ledger, and the checker compares it item by item. When
the verdict reads no cost, the build hours report beside it as its price.

## The ceiling covers the workload

Sample the operator's real work, such as its
recent cases, and count the cases the framing could serve if everything
uncertain went its way. The sample spans every body of work the operator called theirs.
A framing that names one place to test still counts every place, and only a value that
forbids service elsewhere caps the work. The ceiling is a table of the sampled cases,
with the value that reaches or excludes each one. A ceiling stated without that table is
not a count. Count cases in the unit the verdict divides by. When one request yields
several recorded outputs, count requests, and state how many outputs each yields. A case
reached only through a fallback that reads zero on the verdict's measure counts as
reached for the rate and unread for the measure, and the table states that count.
Before marking a case unreached, ask whether the missing part is one the
operator decides. A part the operator decides sits in the request and is reached. For
each case it cannot serve, name the value that excludes it. The ceiling has no
threshold: any case an open value excludes returns that value, whatever its share.
A value from an open axis never caps the workload by default. It returns to the axis
agent, like a value that fails gate 1. Only a fixed axis may cap it, and the card
quotes the operator's words that fix it. A framing that passes with a cap from an open
axis answers a smaller question than the one asked. The ceiling counts the work a value
serves at run time. How many past cases exist to test a value is a resolution question
for step 3, never a ceiling. When the operator names more than one body of work, the
card states for each whether the verdict reads it. A body on which no test source can
reach the resolution floor under the test-input rules is a finding with its count. The
verdict then says it does not speak for that body, and the ceiling still counts it. A
rule that demands a verdict on that body makes the question unsolvable there, and it
returns no row. A framing that claims more than a fixed axis allows has
widened that axis, and it fails gate 1.

## The operator's levers are used

When the question names a lever, such as a preset,
a prior, a representation or a budget, the card says how the method uses it. A method
that ignores a named lever tests the question without its premise.

## The checker

When two counts of one fact disagree, it states both with the method behind each. A count
by text search does not overturn a count by reading the artifacts. A framing that relies
on a class count names the cases in it. The checker recounts the class by a stated method
and reports the framing's cases beside its own. A component or a definition a row adds
with no value behind it goes back to the axis agent. A framing whose statements about one
date or count disagree fails that check until the axis agent reconciles them. Machine
facts are read once, on the day of the check, and every row cites that reading. Before the
checker proposes a rule that returns every row, it asks whether the rule makes the
question unsolvable by construction. Such a rule is a finding about the checker, and it
goes to the study with the operator's words it contradicts.
