---
name: stablemate-code-structure
description: "The language-neutral rules for where code lives *inside* a layer — when a pile of functions becomes an object, when a module becomes two, when a value crossing a boundary needs a name, and where configuration and side effects are allowed to appear. Every rule carries a mechanically detectable trigger, so a violation is a finding rather than a matter of taste. Load when adding a module, growing a parameter list, choosing between a function and a class, or reviewing structure; hexagonal-architecture governs the boundaries *between* layers, and the stack architecture skill (go-architecture, python-architecture, flutter-architecture, typescript-architecture) supplies the mechanics. Applies to **/*.go,**/*.dart,**/*.ts,**/*.tsx,**/*.py."
metadata:
  generated_by: farrier
  source: library/skills/architecture/code-structure/SKILL.md
  resolve: "farrier source .claude/skills/stablemate-code-structure/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
---

# Code Structure — Rules That Can Fire

[`../stablemate-hexagonal-architecture/SKILL.md`](../stablemate-hexagonal-architecture/SKILL.md)
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

## 1. When a pile of functions becomes an object

Three triggers say *yes*. One stop condition says *no*, and it matters as much as the other three —
a codebase that classes everything is as unreadable as one that classes nothing.

### 1.1 A repeated parameter prefix means those parameters are fields

**Statement.** When several functions in a module thread the same leading parameters through each
other, those parameters are an object's state and the functions are its methods.

**Trigger.** Three or more functions taking the same first N parameters (N ≥ 2), passed onward
largely unchanged.

**Fix.** Promote the shared prefix to fields of an immutable object; the functions become methods
taking only what actually varies per call.

```text
# ✗ The first four parameters are identical at every call site and are only ever
#   forwarded. The reader cannot tell which arguments are inputs and which are context.
run_turn(backend, budget, workdir, log, prompt, node_id)
retry_turn(backend, budget, workdir, log, prompt, node_id, attempt)
finish_turn(backend, budget, workdir, log, raw_output)

# ✓ Context becomes state, built once at the edge; each call names only its own inputs.
runner = TurnRunner(backend, budget, workdir, log)
runner.run(prompt, node_id)
runner.retry(prompt, node_id, attempt)
runner.finish(raw_output)
```

A twelve-parameter function is almost never twelve inputs. It is two or three inputs and nine
pieces of context that lost their home.

**Counter-case.** A pure transform whose parameters genuinely vary per call — a formatter, a
comparator, a parser. Repetition of *types* is not repetition of *context*.

### 1.2 Shared mutable module state means that state is the object

**Statement.** Module-level mutable state touched by more than one function is an unnamed object.
Name it.

**Trigger.** Two or more functions in a module read or write the same module-level mutable
variable (including a lock, a cache, a registry, a "current" handle).

**Fix.** Make it a class with those functions as methods and the state as fields. The caller now
decides how many exist and how long they live.

The cost of leaving it implicit is not aesthetic. Module state means **exactly one instance per
process**, chosen by accident rather than by design — so concurrency is off the table, tests
interfere with each other through a channel nobody declared, and the only way to reset it is to
reach into the module and assign.

**Counter-case.** A genuine process-wide singleton whose single-instance nature is the point (a
logger registry, a metrics exporter). Even then, the state belongs to an object; what is
process-wide is the *reference*, held in one place, injected everywhere else.

### 1.3 A mutable cell shared with a closure means the closure set is a class

**Statement.** When a nested function has to mutate a container in its enclosing scope, the
enclosing function has state and wants to be an object.

**Trigger.** A one-element list, a single-key map, or a scratch record created for no reason other
than that an inner function needs to write to it:

```text
fired = {"v": false}          # ✗ a boolean wearing a costume
result = [""]                 # ✗ a string wearing a costume
state  = {"text": "", "session": null, "failed": false}   # ✗ an object wearing a costume
```

**Fix.** Fields on an object, or the language's real primitive for the case — most languages have a
proper one-shot flag or synchronization type, and the hand-rolled cell is worse than it in every
respect.

**Counter-case.** An accumulator local to a single short function with no inner function reading
it. The trigger is *sharing across a closure*, not mutation.

### 1.4 Stop condition — grouping alone does not earn a class

**Statement.** A class must justify itself by **state with invariants** or by **substitutability**
(it is a seam something else can stand in for). Grouping related functions is what a *module* is
for.

**Trigger.** A class with no fields, or whose only field is a value passed identically to every
method.

**Fix.** Delete the class; keep the functions in a well-named module.

A stateless normalizer, an accumulator over plain values, a set of pure conversions — these stay
functions. Wrapping them in an object with no fields adds a construction step, an injection
decision, and a lifetime question, and buys nothing. This is the failure mode "model things as
classes" produces when its stop condition is left unwritten.

---

## 2. When a module becomes two

### 2.1 The docstring test

**Statement.** A module names one capability. You should be able to describe it in a noun phrase
with no "and".

**Trigger.** Its header comment or docstring needs a bulleted list of the unrelated things it does.

**Fix.** One module per bullet, named for the bullet.

This trigger is worth more than its accuracy, because of *when* it fires: while you are writing the
docstring, which is exactly when splitting is still cheap. A module that has already reached the
list-of-bullets stage will keep growing, because every new concern now has precedent.

**Counter-case.** A deliberate facade whose docstring enumerates what it re-exports. A facade
re-exports; it does not implement. If the bullets describe *implementations*, it is not a facade.

### 2.2 The entry point parses and dispatches; it does not do the work

**Statement.** A CLI entry point, HTTP handler, or job main resolves inputs and hands off. Command
bodies live beside their command.

**Trigger.** A file containing both argument/route wiring and the implementation of more than one
command or endpoint.

**Fix.** One module per command, holding that command's argument definition and its body; the entry
point holds only the table that maps a name to it.

---

## 3. Data at boundaries

### 3.1 Round-trip beats provenance

**Statement.** If a value is ever written out and read back — file, wire, subprocess, queue,
another process's memory — that is a **parse boundary**, and one validated model owns both
directions. The writer constructs it; the reader parses it.

**Trigger.** A serialization call taking an inline literal, whose counterpart reader pulls fields
out by key with defaults.

**Fix.** Declare the type once. Writing is "serialize the model"; reading is "parse into the model
and fail loudly if it does not fit".

This is the rule that resolves the question every "validate untrusted input" guideline leaves open:
*what about data my own code wrote?* Provenance is the wrong axis. A checkpoint file written by
trusted in-memory code and read back an hour later has, in between, been exposed to a version
change, a partial write, a disk, and quite possibly a human editing it to unstick a stuck job.
**It does not matter who wrote it; if it survived the process, it is parsed.**

**Counter-case.** A log or event stream that is written and never read back by the program. Output
with no reader has no round trip.

### 3.2 No structured return without a name

**Statement.** A function returning several values returns a named type.

**Trigger** — three detectable forms:

1. A tuple with more than two elements, **or** with two elements of the same type.
2. An untyped map/dict return whose keys are enumerated in the docstring. *The docstring is the
   evidence*: someone knew the shape well enough to write it down, in the one place the compiler
   cannot check.
3. A map/record parameter the function mutates and the caller reads back afterwards.

**Fix.** A record type with named fields. For form 3, return a new value instead of mutating an
argument.

```text
# ✗ Every caller decodes seven positions by counting. Adding a field edits every call site.
stream() -> (text, session, diagnostics, timed_out, rate_limited, reset_at, exit_code)

# ✓
stream() -> TurnResult
```

**Counter-case.** `(value, error)` and `(key, value)`: two elements, different types, universally
understood in the languages that use them. Two same-typed elements is already the trigger, because
`(width, height)` gets called with the arguments swapped eventually.

### 3.3 The typed boundary goes *after* extraction, not at the wire

**Statement.** A foreign payload you do not own — another tool's JSON output, a third-party
webhook, a plugin's event stream — is read **tolerantly** as an untyped map. Your own first
representation of it is where the type starts.

**Trigger.** A strict model whose fields mirror an external system's schema field-for-field.

**Fix.** A tolerant reader that looks for what it needs and shrugs at the rest, producing a typed
value **you** define.

State this explicitly, because a strict reading of 3.1 leads somewhere worse: modeling an upstream
tool's schema converts its next cosmetic rename from "a field we ignore" into "every run crashes".
Owning the schema is what earns strictness. What 3.1 demands is that the *result* of extraction be
typed — not that the wire format be.

**Counter-case.** A payload governed by a contract you share and version (your own API's schema, a
generated client). That one you own; parse it strictly.

---

## 4. Configuration and effects

### 4.1 Configuration is read once at an edge, then injected as an immutable value

**Statement.** Environment variables, config files, and flags are read at the entry point into one
immutable settings object, which is passed down. Nothing below the entry point reads them.

**Trigger.** Any environment or config read at module scope, or anywhere outside the entry point.

**Fix.** One settings type per concern, constructed from the environment at startup, passed
explicitly to whatever needs it. Overrides produce a modified copy, not a mutation.

Two things go wrong without this, and the second is the expensive one. Values read at import time
freeze before a test or a caller can influence them — so the only way to exercise the other branch
is to reload the module. And the same variable read in three modules gives three answers the moment
someone adds a default in two of them.

**Corollary, worth stating separately because it looks fine.** A default parameter value must not
be computed from configuration. In most languages a default is evaluated once, when the function is
defined — configuration that appears live and is not.

```text
def run(prompt, timeout = DEFAULT_TIMEOUT):   # ✗ frozen at definition time
def run(prompt, timeout = null):              # ✓ resolve inside, from injected settings
```

**Counter-case.** The settings object's own constructor. Reading the environment is its job, and it
is at the edge by construction.

### 4.2 A classifier, parser, or mapper performs no I/O — and the clock is I/O

**Statement.** A function whose job is to *decide* or *convert* does not also write files, send
requests, or sleep.

**Trigger.** Ask: can this be exercised with no filesystem, no network, and no waiting? If not, it
is two functions.

**Fix.** Return the decision; let the caller act on it. When timing genuinely belongs to the
component, inject the clock and the sleep as a dependency.

The clock clause is the one people skip, and it is the one that ruins test suites. A retry ladder
that sleeps for real is a suite that either takes minutes or reaches in and patches private names
to avoid it — and neither one tests the ladder. With an injected clock, "wait eight hours for the
rate-limit window" is a microsecond.

**Counter-case.** A function whose *name* is the effect — `persist`, `emit`, `publish`. Those are
supposed to do I/O and are supposed to contain no decisions.

### 4.3 An effect belongs to whoever owns the invariant

**Statement.** When choosing where a side effect lives, ask which object's invariant it maintains —
not which function happened to have the value in scope.

**Trigger.** A write, publish, or cache update in a function whose name promises something else.

**Fix.** Move it to the owner and return the value the caller needs.

Effects settle where the data was convenient, and that is how a pure decision function ends up
holding the only copy of a persistence rule.

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
| 1.1 | 3+ functions sharing the same leading parameters | fields, not parameters |
| 1.2 | 2+ functions touching the same module-level mutable | that state is an object |
| 1.3 | a container created only so a closure can write to it | the closure set is an object |
| 1.4 | a class with no fields | make it a module |
| 2.1 | a module docstring that needs bullets | one module per bullet |
| 2.2 | wiring and >1 command body in one file | one module per command |
| 3.1 | literal in, key-lookup-with-default out | one model owns both directions |
| 3.2 | 3+-tuple, documented map keys, mutated argument | a named record |
| 3.3 | a strict model mirroring a foreign schema | tolerant read, owned type |
| 4.1 | config read at module scope or below the edge | inject immutable settings |
| 4.2 | a decision function that writes or sleeps | split; inject the clock |
| 4.3 | an effect in a function named for something else | move it to the invariant's owner |
| 5 | a test patching a private name | add the injection point |

When you add a rule to this file, add its row. A rule with no row is a preference, and preferences
belong in a review comment rather than a skill.
