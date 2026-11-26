# The clock

Reached from [../SKILL.md](../SKILL.md) before you start tending a process, from a feed or by paying for runs.

A unit reaches the loop from one of two sources, and the loop names which:

- **A feed.** The process delivers on its own. Every notification, ten to thirty minutes
  apart, is a **read** and gets one line in a fixed shape, so lines compare across ticks:

  ```
  <stage> · lap <k>, stage median <m> · turn <elapsed> · doing: <phrase from the transcript> · seen before: <lap or none> · working: <tax in hand, or converged>
  ```

  "Doing" names what the current turn is at, read from its transcript, not from the node
  name. "Seen before" names the earlier lap of this unit that did the same thing, or none.
  "Working" names the tax the attendant is removing between this tick and the next. A line
  without "doing" and "seen before" is a check not made. A line reading "working: none"
  while the table holds a tax is the attendant's own dead time, and it counts like any
  other. A lap count above the stage's median, or a "seen before" that names a lap, starts
  a measure at once, while a rewind can still save the rest of the unit.
- **A paid run.** No feed delivers, so the loop runs the unit itself, at the cheapest rung
  of the instrument ladder under "Change" that reads what the cycle needs. Before each run,
  name the record already paid for that answers the same question, or why none does. A
  record that answers is cited, not re-run.

Every unit delivered, from either source, is a full **measure** and **rank**: the whole
table rebuilt with the new unit, the fresh judge, and the grade of every open cycle.
Between units, the loop runs the diagnose, design and change steps of the top open tax.
