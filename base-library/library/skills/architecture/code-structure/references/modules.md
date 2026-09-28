# When a module becomes two

Three triggers govern module-scale indirection: what the docstring admits, what an entry
point is doing besides dispatching, and when a forwarding wrapper has no second job.

Every rule below is one of the trigger rows in
[the code-structure skill](../SKILL.md); read that table first if you are scanning for
which rule fired.

## 2.1 The docstring test

**Statement.** A module names one capability. You should be able to describe it in a noun phrase
with no "and".

**Trigger.** Its header comment or docstring needs a bulleted list of the unrelated things it does.

**Fix.** One module per bullet, named for the bullet.

This trigger is worth more than its accuracy, because of *when* it fires: while you are writing the
docstring, which is exactly when splitting is still cheap. A module that has already reached the
list-of-bullets stage will keep growing, because every new concern now has precedent.

**Counter-case.** A deliberate facade whose docstring enumerates what it re-exports. A facade
re-exports; it does not implement. If the bullets describe *implementations*, it is not a facade.

## 2.2 The entry point parses and dispatches; it does not do the work

**Statement.** A CLI entry point, HTTP handler, or job main resolves inputs and hands off. Command
bodies live beside their command.

**Trigger.** A file containing both argument/route wiring and the implementation of more than one
command or endpoint.

**Fix.** One module per command, holding that command's argument definition and its body; the entry
point holds only the table that maps a name to it.

## 2.3 One implementation has one body

**Statement.** A required or public function owns its implementation. A private helper earns a
separate name by serving another caller or by separating a different kind of work, not by moving
the same body one hop away.

**Trigger.** A function or method's meaningful body is only a call or returned call to a private
helper defined in the same module; it forwards all or nearly all of its parameters unchanged; and
that helper has no other production call or value reference. An added configuration or
infrastructure argument does not stop the trigger: the caller can resolve it immediately before
the inlined body. A method required by a port or framework still fires — the method is the body the
contract requires, while the one-use helper is optional indirection.

**Fix.** Move the helper's body into its sole caller, resolve any added argument there, and delete
the helper. Keep the public or required name as the one place a reader enters and an implementation
changes.

This is a call-graph rule, not a line-count rule. A substantial helper behind one forwarding
method is more expensive than a substantial method: navigation is mandatory, while reuse is zero.
Tests calling the private helper do not create production reuse; test through the owning public
function or inject the dependency the test needs to control.

**Counter-case.** Keep the helper when it has another production caller or is passed as a callback;
when the caller and helper deliberately separate effects from a pure decision and therefore do not
forward the same parameter set; or when generated code, recursion, or a third-party registration
requires the helper's independent identity. A hoped-for future caller is not a caller.

## 2.4 A section banner mid-file is the split, deferred

**Statement.** A comment that visually separates one named block from the rest of a module — a row
of dashes, equals signs, or similar — announces a second capability the module has already grown,
not a subheading within its one capability. This is 2.1 caught later: nobody revisits a docstring
once it is written, but a banner gets typed at the exact moment a second concern lands, which is
still while splitting is cheap.

**Trigger.** A banner-style divider comment (`# ---...---`, `// ===...===`, and equivalents) that
introduces a named block partway through a module that already implements something else above it.

**Fix.** The section under the banner becomes its own module, named for what the banner calls out.
If the module is already imported by its existing path from outside the package, leave a facade
behind (2.1's counter-case) rather than moving nothing.

**Counter-case.** A divider separating *public API* from *private helpers* within the same
capability, or grouping related constants that all belong to the one thing the module already does.
Those organize one concern; they do not name a second one. The test: can the block under the banner
be titled with a noun phrase that is *not* also a fair title for the whole module? If yes, this
rule fires; if the title would just restate the module's own docstring, it does not.

## 2.5 A shared module never imports from a module that uses it

**Statement.** Code that several features share lives below all of them. A shared module imports
nothing from one feature's package.

**Trigger.** A module that two or more features import, which itself imports from one of those
features. The import graph shows it: an edge from the shared layer (`kit/`, `common/`, `placement`,
`util`) into a feature directory.

**Fix.** Move the imported names down into the shared module, or into a new one beside it named for
what they do. The feature then imports them like everyone else.

The shared helper got written inside the first feature that needed it, and the second feature
imported it from there. From then on the helper keeps that feature's name, and nobody finds it by
reading the shared layer. A generic cell filter that lives in a water module gets rewritten by the
next feature that never thought to look under "water".

**Counter-case.** A plugin registry that imports its plugins in order to list them. That import is
the registry's job, and it runs in one place.

## 2.6 A module's name predicts every name it exports

**Statement.** Each public name in a module shares the module's noun. When a caller imports a name
that the module's name would not lead them to, the name is in the wrong module.

**Trigger.** Either shape fires the rule:

- A module imported by three or more other packages, where most importers use names that do not
  share the module's noun.
- A module named for a thing that no longer exists in it, such as a step's package with no step
  left.

**Fix.** Move each name to the module its noun belongs to, creating that module when it does not
exist. Keep the old module only for the names that match its name.

**Counter-case.** A package facade that re-exports its submodules. The facade's noun is the package,
and every name it exports belongs to that package.

## 2.7 A decoding or a constant has one owner, and everyone else calls it

**Statement.** When a data shape needs decoding, one function decodes it. When a number means
something, one name defines it. Every other module calls that function or imports that name.

**Trigger.** Either shape fires the rule:

- The same loop header over the same structure in two or more modules, for example `for r, row in
  enumerate(mask)`.
- The same named constant assigned the same literal in two or more modules.

**Fix.** Keep the owner's version, delete the copies, and import. When a copy differs from the
owner, decide which behaviour is right before deleting. The difference is usually a bug in the
copy.

A copied decoder does not stay a copy. One copy gets a fix and the others do not, and the map then
disagrees with itself about which cells an object covers.

**Counter-case.** A test that decodes by hand to check the owner. That independence is the test's
point.

## 2.8 Domain facts are queries against their owner, never literals

**Statement.** When a project has a source of truth for its domain, such as a catalogue, an
ontology, a schema or a registry, every domain fact comes from a query against it. A module that
needs a new fact adds a query to the owner.

**Trigger.** Any of these shapes fires the rule:

- String literals naming domain entities, such as object types, asset ids or category names, in a
  module other than the owner. A block of such constants at the top of a feature module is the
  common form.
- A regex or a string slice that extracts a property from an identifier, as in reading a level out
  of an animation name.
- A property computed inline from the owner's raw data that the owner could answer, such as
  counting cells in a footprint mask.

**Fix.** Add a category, a tag or an accessor to the owner, and query it. The feature module keeps
only the policy: how many, how often, which category. It never keeps the membership list.

A literal list of entity names is a second catalogue. It does not learn about the entity the owner
gained last week, it keeps the one the owner dropped, and nobody reviewing the owner sees it.

**Counter-case.** A test fixture that names a specific entity to pin a behaviour. Tests may name
things. Production code asks.

## 2.9 A directory holds one kind of thing

**Statement.** A directory's name says what kind of entry it holds, and every entry is that kind.
Code of another kind lives in a directory named for its kind.

**Trigger.** A directory whose entries are mostly one kind, such as one subpackage per pipeline
stage or one file per command, holding a file or subpackage that is not that kind. Shared helpers
beside the stages are the common form. The codebase map shows it: one line does not fit the
sentence the other lines share.

**Fix.** Move the odd entry to the directory of its kind, creating the directory when none exists.
Write the kind as the first line of the directory's map, so the next misplaced entry contradicts a
written sentence.

The first shared helper lands beside the stages because the stages were its first callers. The
second helper follows the first. After that the directory no longer tells a reader what it holds,
and the helpers accumulate feature imports that rule 2.5 forbids.

**Counter-case.** The package's own entry point or facade, such as an `__init__` that registers the
stages. It serves the directory's kind.

## 2.10 A module that only tests import is deleted or wired in

**Statement.** Every production module has a production caller. A module whose only importers are
tests is dead code that still costs a reader's time.

**Trigger.** Either shape fires the rule:

- A module that no non-test module imports and that is not an entry point.
- A docstring or comment that names modules, scripts or files that no longer exist.

**Fix.** When the behaviour matters, wire it into the path that needs it, such as a check the
pipeline runs. Otherwise delete the module and its tests together.

A dead module still looks like the owner of its concept. The next change finds it by search,
extends it, and never runs it.

**Counter-case.** A library's public API, whose callers live outside the repository, and a
command-line entry point run by hand.
