# Contracts

What a function relies on, and what it promises back. A broken assumption should raise, and a
signature should serve one purpose.

Every rule below is one of the trigger rows in
[the code-structure skill](../SKILL.md). Read that table first when you are scanning for which rule
fired.

## 7.1 "Not computed yet" is never an empty default

**Statement.** A field that a later stage fills starts out marked as not filled, and its reader
checks the mark. An empty collection means "computed, and empty". It never also means "nobody ran
the producer".

**Trigger.** A field that defaults to an empty collection, zero or `None`, together with a comment
or docstring naming the stage or step that fills it.

**Fix.** Pick one of these:

- The consumer receives the value as an argument or pulls it from a registry that raises when it is
  missing. The field goes away.
- The field defaults to a sentinel or `None`, and the reader asserts it is set before using it.
- The producer returns a new record that holds the filled field, and the consumer's type requires
  that record.

An empty default turns a missing stage into a wrong answer. The consumer computes on the empty set,
produces nothing, and the run looks successful. The failure then shows up far downstream as an
output nobody can trace back.

**Counter-case.** A field whose empty value is a legal result and that no other stage fills, such
as an accumulator the same function both creates and consumes.

## 7.2 Only the producer creates. Every consumer requires.

**Statement.** When stages share a value through a registry or a context, one stage creates it. The
others ask for it and fail when it is absent.

**Trigger.** A get-or-create or get-with-default call (`get_or_create(T, T)`, `get(T, T())`,
`dict.setdefault`) for a shared value, in code that is not that value's first producer.

**Fix.** The producer creates the value. Every consumer calls the registry's strict accessor, which
raises with the name of the missing value. When a consumer can run without the producer, it says so
in one line and tests for absence explicitly.

A consumer that creates what it expected to find hides the missing producer. It then works on a
fresh empty object, and rule 7.1 fires further down.

**Counter-case.** A value that has no producer by design, such as a cache or a counter that every
stage may be the first to touch.

## 7.3 A search for something that must exist raises when it finds nothing

**Statement.** When code looks up an element that the rest of the program assumes exists, a failed
lookup raises. Falling through with nothing found is only right when "not found" is a legal outcome.

**Trigger.** Either shape fires the rule:

- A `for` loop with a `break` on a match and no `else` clause, where nothing after the loop checks
  whether the match happened.
- A `next(iter, None)` or `.get(key)` whose `None` result nothing checks.

**Fix.** Add the `else: raise` clause, or use the strict form: `next(iter)`, `mapping[key]`. When
several such lookups share a count, assert the count once after the loop.

**Counter-case.** A search whose miss has a documented meaning that the caller handles, such as an
optional feature being absent.

## 7.4 An early exit comes after the writes other stages read

**Statement.** When a loop body writes shared fields that a later stage reads, every path through
the body writes them. An early `continue` or `return` either sets the fields first or raises.

**Trigger.** A `continue` or early `return` that comes before assignments to shared fields in the
same loop body or function.

**Fix.** Write the fields' fallback values before the exit. When no fallback is correct, raise
instead of skipping.

**Counter-case.** An exit that marks the item as deliberately excluded, in a place the reader
checks. The mark is the write.

## 7.5 A boolean parameter that picks a purpose is two functions

**Statement.** A function serves one purpose. When a boolean argument decides which checks run or
which shape comes back, the function serves two purposes and should be two functions, or one
function that takes the rule set as a value.

**Trigger.** Any of these shapes fires the rule:

- A boolean parameter the callee tests in more than one `if`.
- A caller that computes the flag from a kind, as in `mine = purpose == "MINE"`, and passes it on.
- A boolean that changes the return type.

Ruff's `FBT001` and `FBT002` list the candidates. Most of what they list is configuration, and
configuration is not a hit.

**Fix.** When the flag picks a set of rules, pass the rules as a value, and look them up by kind as
in rule 6.1. When the flag picks a different result shape, split the function into two named for
their results.

**Counter-case.** A flag that configures one behaviour without changing the function's purpose, such
as `verbose`, or a constructor flag that picks a variant the object then keeps.

## 7.6 A planner and a doer are two functions

**Statement.** Code that decides what to do and code that does it are separate. A dry-run mode
turned on by a parameter is a planner hiding inside a doer.

**Trigger.** Either shape fires the rule:

- A signature or a dataclass with two or more optional callable fields.
- A `quiet`, `dry_run` or `plan_only` parameter that some callers set and others do not.

**Fix.** Make the planner a pure function that returns a plan value. The doer takes that plan and
applies it. A caller that only wanted to look calls the planner alone.

When one function carries both jobs, every change to placement risks the planning callers, and
their optional callbacks multiply until each call site reads like a configuration file.

**Counter-case.** A command-line `--dry-run` at the entry point, which calls the planner and prints
the plan instead of calling the doer.
