### `unarranged-interaction-precondition` — a `when:` names a state the scenario cannot reach

This `interaction`/`invocation` arm's `when:` states a precondition — the finding's `message`
quotes it — and nothing in the compiled scenario can arrange that state before the arm's
assertions run. Rather than run the arm against whatever state actually holds and risk a false
result for a state the claim never established, the compiler withholds the arm entirely and
gaps it here.

Add a `fixture:` bullet (or a scaffolded step earlier in the same scenario) that puts the world
into the state `when:` names, naming a fixture node under `docs/features/<surface>/fixtures/<name>.md`
that provides it — or an existing fixture that already does. If nothing can arrange that state
from this surface at all, the `when:` clause may be claiming something this book cannot actually
test yet; say so rather than forcing an arrangement that does not exist.

**This is not `unresolved-precondition`.** That code covers a `verify:`/path reference to a fact
no earlier producer left behind, or a missing request body — mechanics internal to one already-
compiling scenario. This one is specifically an `interaction`/`invocation`'s own `when:` clause
naming a precondition the compiler could not arrange at all.
