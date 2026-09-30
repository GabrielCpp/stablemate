# When a pile of functions becomes an object

Three triggers say a pile of functions has become an object, and one stop condition says it
has not. The stop condition matters as much as the other three — a codebase that classes
everything is as unreadable as one that classes nothing. Rules 1.5 to 1.8 cover the values
objects hand each other. Rules 1.9 to 1.11 cover a behaviour with several variants: the role
they share, who names a variant, and how wide the role is.

Every rule below is one of the trigger rows in
[the code-structure skill](../SKILL.md); read that table first if you are scanning for
which rule fired.

## 1.1 A repeated parameter prefix means those parameters are fields

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

## 1.2 Shared mutable module state means that state is the object

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

## 1.3 A mutable cell shared with a closure means the closure set is a class

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

## 1.4 Stop condition — grouping alone does not earn a class

**Statement.** A class must justify itself by **state with invariants** or by **substitutability**
(it is a seam something else can stand in for). Grouping related functions is what a *module* is
for.

**Trigger.** A class with no fields, or whose only field is a value passed identically to every
method, and that implements no role. A fieldless class that implements a role is a variant (rule
1.9), and the stop condition does not fire.

**Fix.** Delete the class; keep the functions in a well-named module.

A stateless normalizer, an accumulator over plain values, a set of pure conversions — these stay
functions. Wrapping them in an object with no fields adds a construction step, an injection
decision, and a lifetime question, and buys nothing. This is the failure mode "model things as
classes" produces when its stop condition is left unwritten.

## 1.5 A model stores what defines it, not what someone computed from it

**Statement.** A core data model holds the facts that make it what it is. An analysis derived from
those facts is a separate value, owned by the code that computes it and handed to whoever reads it.

**Trigger.** Any of these shapes fires the rule:

- A field on the model that exactly one stage writes, where that stage computes it from the
  model's other fields.
- A cache inside the model that indexes that derived field and invalidates itself by checking
  whether the field changed, for example `if self._key != id(self.zones)`.
- A model docstring that justifies a field by the reader who wants it rather than by what the model
  is.

**Fix.** Remove the field. The producing stage returns the analysis as its own typed value, and each
consumer receives that value explicitly. When a view needs model facts and the analysis together,
it takes both.

A grid that also carries its segmentation has two sources of truth. The terrain can change after
segmentation ran, and nothing tells the stored zones they are stale. Every reader of the model now
depends on the segmentation stage, including readers that only wanted tiles.

**Counter-case.** A derived value the model maintains itself on every write, such as a count kept
beside a list. The model owns that invariant and cannot drift from it.

## 1.6 One thing, one model

**Statement.** Each domain entity has one model in the program. Another representation of it, such
as a file format or a corpus loader's record, is converted into that model at the edge. Code past
the edge queries the one model.

**Trigger.** A function that takes a second representation of an entity the project already
models, and rebuilds an answer the main model already gives. A hand-built boolean grid of blocked
tiles next to a map model that already answers "is this tile blocked" is the common form.

**Fix.** Convert the second representation with the project's reader, or write that reader. Then
call the main model's query. Delete the rebuilt one.

Two models of one thing disagree the first time either changes. The rebuilt query also repeats
every decision the main model makes, such as which footprint cells block, so a fix in one never
reaches the other.

**Counter-case.** The reader or writer for that representation. Converting is its whole job.

## 1.7 An index answers questions and never changes after it is built

**Statement.** An object built once so that later code can ask it questions is a value. It changes
in its constructor and nowhere else. Its methods answer questions about the data it holds. A
computation that brings its own inputs or its own policy is a function that takes what the index
returns.

**Trigger.** Any of these shapes fires the rule:

- A stage builds an object and hands it to later stages, and a later stage writes one of its fields
  or a container inside it, for example `record.used.add(t)`.
- Code snapshots such an object and restores it to undo a failed attempt.
- A method on the index takes a tuning parameter, a threshold or a random generator.
- A method fills a cache on its first call.

**Fix.** Freeze the index, and do all its work in its constructor or in the function that builds
it. Move the part that changes to the one object that owns the invariant it tracks, as rule 4.3
says, and give that owner the undo. Move a method that needs outside inputs out to a function.

```text
# ✗ The index is shared, and later stages write claims into its records.
index = build_zone_index(workspace)
index.records[z].used.add(t)                   # one stage claims a tile
snap = [set(r.used) for r in index.records]    # another stage rolls back by hand

# ✓ The index only answers. Claims live with the object that refuses overlaps.
index = ZoneIndex.build(labels)
index.fronts(z)
mark = cover.mark()
cover.claim(cells)
cover.rollback(mark)
```

A shared index that changes makes call order part of every reader's input. A stage that reads it
sees whatever each earlier stage wrote, and nothing in its signature says so. The hand-written
snapshot is the symptom. The code had to write its own transaction because no owner offered one.

**Counter-case.** An object whose job is to keep a changing invariant, such as a cover index that
refuses overlapping objects. That is state with invariants under rule 1.4, and it offers the writes
itself. The trigger is a write from outside into an object that exists to be read.

## 1.8 A function takes what it reads

**Statement.** A function's parameters name the data it uses. It does not take a container in order
to reach one or two fields inside it.

**Trigger.** A parameter typed as a stage-wide container, such as a workspace, a registry, an index
or a statistics record, where the function body reads at most two of its fields and passes it
nowhere else.

**Fix.** Pass those fields. The caller does the lookup.

```text
# ✗ Takes the whole zone map and an id, and uses them only to find one zone's fronts.
gate_bands(tiles, zones, zone_id, open_frac)

# ✓ The caller asks the index. A test calls this with a handful of tiles.
gate_bands(tiles, index.fronts(zone_id), open_frac)
```

A test of the wide version must build the whole container to exercise one field of it. The
signature hides which data the function depends on. Every change to the container becomes a
possible change to the function, so a reviewer has to read the body to rule it out.

**Counter-case.** A function whose job is the whole object, such as a renderer or a serializer. A
method of the container itself. Rule 1.1 also wins when several functions take the same fields,
because those fields are then an object's state and the object is the right parameter. The trigger
is a large container used thinly, not a small one used fully.

## 1.9 A variant implements a role. It never extends another variant

**Statement.** When two or more implementations can stand in for each other, they are variants of
one role. The role is an interface the consumer owns. Each variant implements that interface, and
no variant inherits from another.

**Trigger.** Either shape fires the rule:

- A class that extends a concrete class of the same codebase: one that is itself instantiated,
  or that declares no abstract member.
- A subclass whose overrides only return a different function, class or constant than its
  parent's.

**Fix.** Name the role after what the consumer asks of it, and declare it as an interface. Make
each variant its own implementation, in its own module. Code the variants share becomes a
collaborator each one holds as a field, or a set of functions each one calls. The consumer takes
the role as a parameter, and the entry point picks the variant.

```text
# ✗ The second variant is a subclass of the first. The type says a PDF report is an HTML report.
class PdfReport(HtmlReport):
    def _render(self, doc): return render_pdf(doc)

# ✓ One report, one role, two implementations. The entry point chooses.
class Renderer(Protocol):
    def render(self, doc: Document) -> bytes: ...
class HtmlRenderer: ...
class PdfRenderer: ...
Report(renderer=PdfRenderer())
```

Inheriting from a working class reuses its code and claims to be a kind of it in one move. The
claim is false for a sibling variant, so every reader who trusts the type is misled. The parent
cannot change without checking a subclass that was never meant to be one, and a third variant has
to pick which sibling to extend.

**Counter-case.** A base class the framework requires, such as an exception hierarchy or a UI
widget. A test double that subclasses the null implementation of a port. A variant written as a
parameterised instance of one class, when the variants differ only in data (rule 6.2).

## 1.10 A consumer names the role, never a variant

**Statement.** Code that uses one of several variants depends on the role alone. Only the entry
point, where the program is assembled, imports a variant by name.

**Trigger.** Either shape fires the rule, once a second variant exists:

- A module outside the entry point that imports a specific variant in order to call it.
- A consumer that imports the role from a module that also imports the variants, such as the
  module holding the name table. The consumer then loads every variant to learn one type.
- A parameter typed by the role whose default value is one variant.

**Fix.** Make the parameter required and typed by the role. Move the choice, and the import of
each variant, to the entry point. A configuration value names the variant, and a table at the
entry point maps the name to it (rule 6.1). Declare the role beside its consumer, or in a
module of its own that imports no variant.

A default variant below the entry point is a decision made twice. The entry point's choice
overrides it on one path, and every other path, including the tests, quietly runs the default.

**Counter-case.** A role with one implementation and no second one on the table. A plain call is
right there, and the role is extracted when the second variant arrives.

## 1.11 A role is as wide as its consumer's use

**Statement.** An interface declares what its consumer calls, and nothing more. Two consumers
that call different things are two roles.

**Trigger.** Either shape fires the rule:

- An implementation that fills a member with a stub, such as raising "not implemented", passing,
  or returning a placeholder, only to satisfy the interface.
- An interface whose consumers each call a disjoint subset of its members.

**Fix.** Split the interface along the consumers' use. A class that serves both consumers
implements both roles.

**Counter-case.** A null object, whose empty members are its purpose.
