# A verdict that depends on something outside the test

A flaky test is a test whose verdict depends on something other than the code it tests. Each row
names one outside thing by the shape it leaves in the test. The stack skill gives the spelling to
search for. A stack with no spelling still has the rule, and its shapes are found by reading.

Each row has a trigger, a fix, a counter-case where the shape is harmless, and a proof. The proof
disturbs the outside thing on purpose: the test goes red before the fix and stays green after it.

## 15.1 The test reads product source as text

**Trigger.** The test opens a source file of the code under test, or asks the runtime for a
function's source, and asserts on the text.

**Why it flakes.** The suite loaded the code once. The file on disk belongs to whoever edits the
checkout next, so the text read later is not the code that is running.

**Fix.** Call the code and assert on what it returns or does. When the contract is structural, such
as "every flow passes this argument", build the object and assert on what it produces.

**Counter-case.** The file is a fixture under the test folder. A guard whose whole job is to read
the tree is a check, not a test (§13), and it runs on a still copy.

**Proof.** Change the source file on disk while the test runs. The verdict does not move.

## 15.2 The test reads a checkout it did not create

**Trigger.** The test runs version control, or walks a working tree, in a folder the test did not
build. The usual shape is a command run in the repository root or the current directory.

**Fix.** Build the repository in the test's own temporary folder, with the commits the test needs.

**Counter-case.** None. A checkout the test did not create has a branch, a dirty state and a
neighbour session that the test cannot know.

**Proof.** Run the test from a dirty checkout, then from a detached one. Same verdict.

## 15.3 The test waits on the clock

**Trigger.** The test sleeps, delays or pauses for a set time. The pause may come before an
assertion, or stand in for "give it a moment" between two steps.

**Why it flakes.** The pause is a guess at how long the work takes. A loaded machine takes longer
than the guess, and a quiet one pays the whole pause for nothing.

**Fix.** Wait on the event the work produces: a line of output, a file, a state, a signal. Give the
wait a deadline many times longer than the work ever takes. The deadline is a safety net for a hung
test and measures nothing. Where the work offers no event to block on, poll its condition. The
condition ends the loop, and the pause between two reads only paces it.

A claim that nothing happened needs an event too. Start a second piece of work that the code
handles after the first, wait for its result, then assert the first left no trace.

Time the product itself counts, such as a debounce, a poll interval, a backoff or an expiry, comes
from an injected clock or the runner's fake timers. The test advances it.

**Counter-case.** None. A fake that must hold its answer blocks on an event the test sets.

**Proof.** Run the test while the machine is loaded, for example beside several copies of the suite.
Same verdict.

## 15.4 An assertion bounds elapsed time from above

**Trigger.** The test reads the clock twice and asserts the difference is below a number, or sets a
short timeout on a wait it expects to succeed.

**Fix.** Inject the clock and advance it by hand. Where the claim is about order, assert the order
of events.

**Counter-case.** The test is a benchmark, marked as one and kept out of the default suite.

**Proof.** The same loaded run as 15.3.

## 15.5 The test opens an address named by a literal

**Trigger.** A port, a file path, a socket name or a lock name is written as a literal and the test
opens, binds or creates it.

**Fix.** Ask the system for a free one. A port comes from binding port zero and reading the port
back. A path lives under the test's temporary folder.

**Counter-case.** The literal is only text. Nothing opens it.

**Proof.** Run two copies of the test at the same time. Both pass.

## 15.6 The code reaches the user's machine and the test did not redirect it

**Trigger.** The code under test reads or writes the home folder, a user cache, a user config or an
environment variable, and no fixture pointed that place at the test's temporary folder. A test that
assigns to the process environment directly is the same shape from the other side.

**Fix.** One suite-wide fixture redirects home, cache and config for every test. A test changes the
environment only through the harness tool that reverts the change at teardown.

**Counter-case.** The place is a parameter and the test passes its own folder.

**Proof.** Run the suite with home pointing at an empty folder, then at a full one. Same verdicts,
and both folders are unchanged afterwards.

## 15.7 The test starts work that no teardown ends

**Trigger.** The test starts a process, a thread or a background task, and no fixture teardown or
cleanup block ends it. A process that starts children of its own needs the whole group ended.

**Fix.** The fixture that starts the work owns it. Teardown ends it and waits for it, children
included, whether the test passed or failed. The suite fails at its end when a child survives.

**Counter-case.** The harness owns the work through a scoped construct that ends it on exit.

**Proof.** Make the test fail halfway. Nothing it started is alive after the run.

## 15.8 A value shared across tests is changed by one of them

**Trigger.** A fixture wider than one test hands out a value a test mutates. A module-level value or
a cache in the product is filled by one test and read by the next.

**Fix.** Scope the fixture to one test or hand out a copy. Clear a product cache in a suite-wide
fixture.

**Counter-case.** The shared value cannot be changed.

**Proof.** Run the suite in random order, then run the test alone. Same verdict.

## 15.9 A module acts outside itself when it is loaded

**Trigger.** A statement at the top level of a module, product or test, changes something the
module does not own: the search path for imports, the environment, the working directory, a signal
handler, an exit hook, the root logger, a file, a socket, a process, or a value held by another
module.

**Why it flakes.** Loading happens once per process, in whatever order the run reaches the modules.
The change is in place for every test that runs after the load and for none that runs before. A
test then passes only when some other module was loaded first, and fails alone.

**Fix.** Loading a module builds that module's own values and nothing else: a constant, a table, a
compiled pattern, a configured object of a library it uses. The outside change moves into a
function, and whoever needs it calls it: the entry point for the product, a fixture for a test. A
fixture undoes the change at teardown. A setting the runner offers, such as a search path in its
configuration file, replaces a statement that edits the path.

**Counter-case.** None. A skip the runner offers at the top of a test module is the runner's own
mechanism and changes nothing outside the module.

**Proof.** Run each test file alone, in a fresh process. Same verdict as in the suite.

## The hunt

Reading finds rows 15.1, 15.2, 15.5, 15.6 and 15.9 whole. Rows 15.3, 15.4, 15.7 and 15.8 hide in shapes
no table lists, so a run judges them:

1. Pin a copy of the code that nobody edits.
2. Run the suite on it several times, in random order, with the machine loaded.
3. A test whose verdict changed between runs is flaky by measurement. Run it alone to learn which
   row it is: red alone is a broken test, green alone is rows 15.3 to 15.8.

A retry marker on a flaky test hides the row and keeps the dependence. Fix the row.

A row with no counter-case is a rule a machine can hold. Turn it into a check that fails the suite,
so the next test of that shape is refused when it is written.
