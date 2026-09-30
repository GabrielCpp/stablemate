---
name: code-structure
description: "Language-neutral rules for where code lives inside one layer: when functions become an object, when a module splits, where configuration, environment facts and side effects may appear, when a branch chain is a table, and which assumptions must raise. Each rule has a trigger a reader or a grep can detect. Load when choosing between a function and a class, adding a second way to do something the code already does, growing a parameter list or a module, adding a setting or a file path, reading a value another stage fills, or reviewing structure. hexagonal-architecture covers the boundaries between layers. Applies to **/*.go,**/*.dart,**/*.ts,**/*.tsx,**/*.py."
applyTo: "**/*.go,**/*.dart,**/*.ts,**/*.tsx,**/*.py"
tags: [standards]
---

# Code Structure — Rules That Can Fire

[`{{ instruction_file("hexagonal-architecture") }}`]({{ instruction_file("hexagonal-architecture") }})
governs the boundaries **between** rings: which way dependencies point, what a port may name, where
infrastructure is allowed to live. This skill governs the inside of a single ring — the decisions
that never trip a layering check and produce most of the damage anyway: a 1,600-line module, a
twelve-parameter function, a dict returned where a type belonged, an environment variable read at
import time.

## Every rule owes a trigger

Most structural guidance is unfalsifiable. "Prefer small modules." "Model state and behavior as a
class." Both are true; neither has ever stopped anyone, because you get to decide *after the fact*
whether the module was small enough or the behavior meaningful. Compare a rule like "no relative
imports": it fires, so it holds.

So every rule below has four parts, and a candidate rule that cannot fill all four does not belong
in this file:

| Part | What it must be |
|---|---|
| **Statement** | what to do |
| **Trigger** | a *shape in the code* a reader or a grep can detect — never a judgment |
| **Fix** | the specific transformation |
| **Counter-case** | when the trigger fires and you are still right |

The counter-case is not politeness. A rule with no stated exception gets applied where it does
harm, and then gets abandoned entirely.

---

## How to use this file

**Scan the trigger table at the bottom.** It is the whole rule set, one row per rule, each row a
shape you can detect by reading or grepping. Nothing else here is needed to *notice* a violation.

When a row fires, open the file holding it for the statement, the fix, the counter-case, and the
reason the rule exists. Each carries a quarter of the rule set:

- **[references/objects.md](references/objects.md)** — rules 1.1–1.4. When a pile of functions
  becomes an object, and the stop condition that says it does not. Read it when you are weighing a
  function against a class, growing a parameter list, or looking at module-level mutable state.
- **[references/modules.md](references/modules.md)** — rules 2.1–2.4. When one module is really
  two, or one function is only a corridor to another. Read it when writing a module's docstring,
  when an entry point started doing the work, when a private helper has only one caller, or when a
  section banner just went into a file that already does something else.
- **[references/boundaries.md](references/boundaries.md)** — rules 3.1–3.3. Values written and read
  back, returns with several pieces, and payloads from a schema you do not own. Read it when
  designing a checkpoint, a wire format, or a reader for another tool's output.
- **[references/config-and-effects.md](references/config-and-effects.md)** — rules 4.1–4.3. Where
  configuration may be read and where a side effect may live. Read it when adding a setting, a
  file path, a default parameter, a cache write, or a `sleep`.

- **[references/control-flow.md](references/control-flow.md)**: rules 6.1 to 6.5. When a branch
  chain is a table, and when a loop is doing more than one job. Read it when you write an `elif` on
  a kind, copy a function to change its numbers, nest a loop, or add a fallback pass.
- **[references/contracts.md](references/contracts.md)**: rules 7.1 to 7.6. Which assumptions must
  raise, and when a signature serves two purposes. Read it when a field is filled by another stage,
  when you search for something that must exist, or when you add a boolean or optional callback
  parameter.

Rules 2.5 to 2.10 in modules.md cover where shared code lives: below every feature that uses it,
in a module whose name predicts it, in a directory of its kind, with one owner per decoding,
constant and domain fact, and no module that only tests import. Rules 1.5 to 1.8 in objects.md
keep derived analysis off a core model, keep one model per entity, keep an index read-only after it
is built, and keep a function's parameters to the data it reads.

Rules 1.9 to 1.11 in objects.md cover variants: a second implementation of something the code
already does implements a role the consumer owns, the consumer never names a variant, and the role
stays as narrow as its use.

Rule 5 stays here, because it is the one to carry without looking anything up.

## SOLID is decided in the design and detected here

The five SOLID principles are design outcomes. They hold when the roles and the variants are named
before the code is written, which is the job of
[`{{ instruction_file("decompose") }}`]({{ instruction_file("decompose") }}). Load it before
adding a second way to do something the code already does, even when the request reads as wiring,
such as "add an option to switch between X and Y". The rules below are how a reader detects,
after the fact, a principle the design missed.

| Principle | What breaks it | Rules that fire |
|---|---|---|
| Single responsibility | a module or concept that needs "and" to describe | 2.1, 2.4, 6.3 |
| Open/closed | a new variant added by editing the consumer or subclassing a sibling | 1.9, 6.1, 7.5 |
| Liskov substitution | a variant that extends another variant instead of the role | 1.9 |
| Interface segregation | a role with members its consumer never calls | 1.11 |
| Dependency inversion | a consumer or shared module that names one variant | 1.10, 2.5 |

---

## 5. The question that catches most of the above

**A monkeypatched private name is a missing injection point.**

**Trigger.** A test that reaches into a module and replaces a private/internal function, or that
reassigns module state to set up a scenario.

**Fix.** Whatever the test needed to control is a dependency. Inject it.

Keep this one close, because it is the cheapest available proxy for every rule here. Ports that
name only domain types, absent collaborators that are null objects, injected settings, classifiers
free of I/O, an injected clock — all of them pay off in one observable currency: **can this be
tested without patching?** A reviewer who cannot recall the taxonomy can still ask that.

The tell that a patch-based seam has gone wrong is when a test must know the *wrong component's*
internals to set up its scenario — faking any backend's failure by patching one specific backend's
private function, say. At that point the seam is not merely informal, it is in the wrong place.

**Counter-case.** Patching at a genuine third-party boundary you do not own and cannot inject
around — the standard library's clock, the process table. Prefer a thin owned wrapper even there,
but this is the exception that is real.

---

## Summary of triggers

| # | Trigger — the shape you can detect | Rule |
|---|---|---|
| [1.1](references/objects.md) | 3+ functions sharing the same leading parameters | fields, not parameters |
| [1.2](references/objects.md) | 2+ functions touching the same module-level mutable | that state is an object |
| [1.3](references/objects.md) | a container created only so a closure can write to it | the closure set is an object |
| [1.4](references/objects.md) | a class with no fields | make it a module |
| [1.5](references/objects.md) | a model field one stage derives from the model's other fields | its own value, passed explicitly |
| [1.6](references/objects.md) | a second representation rebuilding a query the main model answers | convert at the edge |
| [1.7](references/objects.md) | a later stage writing into an index it was handed, or snapshotting it to undo | freeze it, the owner takes the writes |
| [1.8](references/objects.md) | a container parameter whose body reads one or two of its fields | pass the fields |
| [1.9](references/objects.md) | a class extending a concrete class, or an override that only swaps a function | one role, one implementation per variant |
| [1.10](references/objects.md) | a variant imported, or defaulted, outside the entry point | take the role; the entry point picks |
| [1.11](references/objects.md) | a stubbed interface member, or consumers using disjoint subsets | split the role |
| [2.1](references/modules.md) | a module docstring that needs bullets | one module per bullet |
| [2.2](references/modules.md) | wiring and >1 command body in one file | one module per command |
| [2.3](references/modules.md) | one caller only forwards to one private helper | inline the helper |
| [2.4](references/modules.md) | a banner-style divider comment naming a new section mid-file | that section is its own module |
| [2.5](references/modules.md) | a shared module importing from one feature that uses it | move the names down |
| [2.6](references/modules.md) | importers use names that don't share the module's noun | move each name to its noun |
| [2.7](references/modules.md) | the same decode loop or constant literal in two modules | one owner, import it |
| [2.8](references/modules.md) | domain entity names as literals outside their owner | query the owner |
| [2.9](references/modules.md) | an entry that isn't the kind its directory holds | move it to its kind |
| [2.10](references/modules.md) | a module only tests import, or a doc naming files that are gone | wire it or delete it |
| [3.1](references/boundaries.md) | literal in, key-lookup-with-default out | one model owns both directions |
| [3.2](references/boundaries.md) | 3+-tuple, documented map keys, mutated argument | a named record |
| [3.3](references/boundaries.md) | a strict model mirroring a foreign schema | tolerant read, owned type |
| [4.1](references/config-and-effects.md) | config read, or an environment fact written, below the edge | inject immutable settings |
| [4.2](references/config-and-effects.md) | a decision function that writes or sleeps | split; inject the clock |
| [4.3](references/config-and-effects.md) | an effect in a function named for something else | move it to the invariant's owner |
| [5](#5-the-question-that-catches-most-of-the-above) | a test patching a private name | add the injection point |
| [6.1](references/control-flow.md) | `elif` chain comparing one value to literals | a table keyed by kind |
| [6.2](references/control-flow.md) | two bodies differing only in literals | one function, one record per variant |
| [6.3](references/control-flow.md) | `break` + `continue` + flag in one loop, nesting > 4 | name each job |
| [6.4](references/control-flow.md) | the same iterable looped twice under a `force` flag | caller walks the rule sets |
| [6.5](references/control-flow.md) | threshold chains, or passes each with a fallback | options as a weighted list |
| [7.1](references/contracts.md) | empty default on a field another stage fills | strict accessor or sentinel |
| [7.2](references/contracts.md) | get-or-create for a shared value outside its producer | consumers require |
| [7.3](references/contracts.md) | `for` + `break` with no `else` for a must-exist search | raise on miss |
| [7.4](references/contracts.md) | `continue` before writes a later stage reads | write the fallback or raise |
| [7.5](references/contracts.md) | a boolean tested in several `if`s, or derived from a kind | pass rules as a value |
| [7.6](references/contracts.md) | 2+ optional callbacks, or a `quiet`/`dry_run` parameter | planner returns a plan |

When you add a rule to this file, add its row. A rule with no row is a preference, and preferences
belong in a review comment rather than a skill.
