### `unparsed-check` — the bullet is not a call from the check vocabulary

`verify:` holds **one call** from ostler's check vocabulary and nothing else. Run `ostler checks` to
see the calls, their arguments and — the part that matters here — the defect each one excludes.

What this finding almost always is, on a book written before `tests:` existed: a **test id parked on
`verify:`**. `- verify: PRED-QA-0142` names the scenario that runs, not the observation it makes.

Repair it in two moves, never one:

1. **Move the id to `tests:`.** That is the slot for "which suite proves this" — a real
   `path::symbol` or the suite's own id, whichever the book uses elsewhere on this node.
2. **Write the observation on `verify:`.** Read the `does:`/`returns:`/`raises:` bullet the id was
   attached to, and declare the check that would go red if that claim were false. The id told you
   *something runs*; it never told you what the run asserts, so you have to read the source (or the
   test, if the citation resolves) to say.

Other shapes of the same finding: prose (`- verify: the receipt is stored`), a bare status code
(`- verify: 201`), a shell command. All of them get the same treatment — the sentence is the *claim*
and belongs on the normative bullet or in prose; the call is what replaces it.

**Deleting the bullet is not the repair.** A node that had a test id at least recorded that
something covered it; a node with neither the id nor a check has been made green by forgetting.
