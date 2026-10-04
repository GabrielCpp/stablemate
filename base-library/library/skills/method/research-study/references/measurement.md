# Measurement

The rules of [`research-study`](../SKILL.md) for the cases its steps name in short: a
generated benchmark, a purpose stated as a share, a method that learns, a repeated unit,
the two controls, the consumer's ceiling and leaks.

## A generated benchmark

A generated benchmark needs a census first: sample real instances of the workload, sort
them by the shape the generator makes, and count. A shape that is 4% of real work caps
any method on it at 4% of the purpose, however well it scores on the benchmark.

## A purpose stated as a share

When the purpose is a margin over a control, state the target as a **share of the
control's shortfall**, not as a fixed number of points. "+10 points" is a fifth of the
shortfall when the control scores 50%, and out of reach when it scores 95%, and nobody
knows which until the control runs. Name the reference the shortfall is measured to:
100%, an oracle, or a stronger system the method must approach. "The small model with the
method closes 30% of its gap to the large model" is a purpose. Fix the share now, before
any number is read, so it cannot drift toward what the data allows.

Add the **resolution floor**: the smallest shortfall, in cases per seed, that can resolve
the share. One lucky case meets any share of a shortfall of three.

For a share, run the control and the reference too, and write the shortfall per seed as a
count of cases. A shortfall under the resolution floor means the benchmark cannot read the
purpose. Grow it or change it before any method runs. That is a fact about the benchmark,
not a result about the method. Convert the share into the count of cases the method must
win per seed, and write it into the baseline row.

Run the control on every seed before any method runs. When its spread across seeds is as
large as the margin the share asks for, one lucky seed can meet the share. Add seeds or
cases until the margin clears the spread.

## A method that learns

When the method learns, hold part of the yardstick out of its training and score only on
that part. A method that scores on the cases it trained on has shown memory.

## A repeated unit

Run one unit twice on the same seed and compare the outputs. When they differ, the arms
cannot be compared until the source of the difference is pinned, such as a thread count
or an unseeded shuffle. A later apparatus change, such as batching or a faster runtime,
must reproduce that output too. When it does not, it starts a new baseline.

## Controls

The field always holds the **no-method control**: the simplest mechanism that uses none of
the idea under test, such as brute-force search, a fixed rule, or the unchanged system
given the same extra compute. Measure it early. When it matches the method, the yardstick
cannot credit the method, and that is a finding about the yardstick. Give the control
every move the fault can need. A control that can change only one kind of part cannot fail on
faults in another kind and then count as the control for them.

The field also holds the **broken-link control**: the method's own output, attached to
the wrong case or the wrong site. A method that beats the no-method control and ties the
broken-link control wins on what it adds, such as more text or more compute, and not on
the link it claims.

## The consumer's ceiling

A method's output often reaches the purpose through
another system: a model that acts on advice, a person who reads a report, a tool with its
own input rules. Hand that system the perfect output before building the method's run. If
the oracle does not clear the bar, no method can, and the gap is in how the output is
delivered. Hand it the same format filled in by the no-method control as well, so the
format cannot take the method's credit.

## Leaks

List every route by which the answer could
reach the measured path without the method: an oracle value, a name that spells the
answer, a template, a check that tells the agent more than the method would. Test each
route with a script over the generated inputs, because reading the generator misses what
the inputs hold. Then remove the method's learned part, such as zeroed weights or a
shuffled table, and confirm the result falls to the control. A result that survives its
own removal came from somewhere else.
