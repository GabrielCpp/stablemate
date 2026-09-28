# Control flow

When a branch chain is really a table, and when a loop is doing more than one job.

Every rule below is one of the trigger rows in
[the code-structure skill](../SKILL.md). Read that table first when you are scanning for which rule
fired.

## 6.1 A branch chain on a kind is a table

**Statement.** When code picks behaviour by comparing one value against a list of names, the names
and their behaviours are a table. Write the table once and look the name up.

**Trigger.** Either shape fires the rule:

- An `if`/`elif` or `switch` chain of two or more branches comparing the same expression to string
  or enum literals.
- The same expression compared to the same literals in two or more functions.

**Fix.** A mapping from the kind to a small object or function that carries each branch's
behaviour. The caller does one lookup. A kind with no entry raises. When the same kind is tested in
several functions, the entry holds one field per function, so adding a kind is one new row.

The chain is cheap the first time. The second function that tests the same kinds copies the chain,
and from then on a new kind has to be added in every copy. The copy that gets missed falls through
to its `else` and silently does the default thing.

**Counter-case.** Two branches that will stay two, such as a success case and a failure case. A
table for two fixed cases is ceremony.

## 6.2 Branches that differ only in data are one branch and a table

**Statement.** When two functions, or two branches, have the same steps and differ only in the
numbers, weights or names they use, the differences are data. Write the steps once.

**Trigger.** Two function bodies of the same statement shape whose differing tokens are all
literals. A structural clone detector finds them. By eye: put the two side by side and every
difference is a number or a string.

**Fix.** One function that takes the differing values as a record, plus one record per variant,
named for the variant.

**Counter-case.** Two functions that share a shape today but serve owners who will change them for
different reasons. Keep them apart and say so in one line where they are defined.

## 6.3 A loop does one job

**Statement.** A loop filters, or transforms, or accumulates, or searches. When one loop body does
three of those, the loop is several functions sharing one set of local variables.

**Trigger.** Any of these shapes fires the rule:

- One loop body that holds both `break` and `continue`, plus a flag variable the loop sets and
  something after the loop reads.
- Blocks nested more than four deep. Ruff reports this as `PLR1702`.
- A loop whose iterable is drawn at random many times over (`rng.choices(cands, k=50 * n)`) and
  which stops on a counter. That is a retry loop mixed with the placement logic.

**Fix.** Name each job. A search becomes a function that returns the found element or `None`. A
filter becomes a predicate or a generator. A retry becomes a helper that takes the attempt as a
callable, for example `place_spaced(cands, n, min_sep, try_place)`. The remaining loop reads as one
sentence.

A flag carried out of a loop is a return value that has no function to return from. Every reader
has to trace every path that sets it, and every path that forgot to.

**Counter-case.** A hot loop where one pass over the data is the point and profiling shows it. Keep
the loop and write its invariant above it.

## 6.4 The caller owns the relaxation ladder

**Statement.** When a task tries strict rules first and falls back to looser ones, the list of
rule sets is one value and the caller walks it. The worker tries one rule set and reports success
or failure.

**Trigger.** The same iterable looped twice in one function, where the second loop runs under a
flag such as `force` or `fallback` and differs only in which checks it skips.

**Fix.** The worker takes the rules as an argument and returns a result or `None`. The caller holds
`for rules in (STRICT, RELAXED): if (r := try_place(rules)) is not None: return r`.

The ladder in the worker is invisible to the caller. The caller cannot tell whether a result met
the strict rules or only the loose ones, and a later reader who adds a third rung has to find both
loops.

**Counter-case.** A single fallback that belongs to the domain rule itself, and that no caller
would ever want to turn off.

## 6.5 A policy written as code is a table

**Statement.** When code decides what to produce by chaining thresholds, fallbacks and passes, the
policy is data: a list of options with weights or an order. One loop walks the list.

**Trigger.** Any of these shapes fires the rule:

- An `if roll < a ... if roll < b ...` chain over one random draw, which is a weighted choice
  written out by hand.
- A fixed sequence of passes over the same items, each pass with its own loop and its own fallback.
- A function whose body tries option A, then B, then C, each written out in full.

**Fix.** Write the options as a list of records, each naming what to produce and its weight or rank.
Draw from it with the language's weighted choice, or walk it in order. The passes become one loop
over the items and one loop over the options.

Hand-written thresholds are cumulative, so changing one option's share silently changes the next
one's. The passes each re-implement the same visit, skip and claim logic, and they drift apart.

**Counter-case.** Two options that will stay two. A single `if` reads better than a table of two.
