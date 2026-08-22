The operator's standing answer to any grill, for a benchmark run.

`author` opens with a grill gate that blocks unconditionally — `operator_mode` does not
gate it, because the premise is that these decisions belong to a person. A benchmark has
no person, so without a standing answer no suite can run `author` at all.

The text below the rule is what the harness writes into `_author-context.md`. It is
deliberately **scope-neutral**: it settles nothing the backlog did not already settle, and
it hands every open question back as a design decision. That is not laziness — it is the
only answer that keeps one run comparable to the next and, for a `design:` suite, the only
answer that does not leak. A grill asks precisely the questions whose answers are the thing
being measured ("is locale switching per-person, or a switcher on the page?"); an operator
who answers that has told the workflow what to design, and every design score after it
measures transcription.

A per-suite override goes in the spec as `grill:`, naming a file beside it.

---

I am the stakeholder who wrote the backlog, and the backlog is the whole of what I have
specified. I am not going to add to it or take anything out of it.

Everything you asked about is a design decision, and it is yours. Decide each one, write
the decision down where the next person will find it, and build to it. Two rules for how
to decide:

- **Scope**: a capability is in scope if a person using the app as the backlog describes
  it would need that capability to use the app at all. If they would, it is in — do not
  wait to be told. If it is a separate product ambition, leave it out and say so.
- **Shape**: pick what a competent team would pick for an app of this size, and prefer the
  choice that is ordinary over the choice that is clever.

Where two of my bullets seem to disagree, resolve it the way that leaves a person able to
finish what they started, and note the resolution.

Do not come back to me for a decision this answer covers. Come back only if you find
something that would cost real money, needs a credential I have not given you, or
contradicts the backlog outright.
