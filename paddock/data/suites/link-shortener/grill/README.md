# The frozen grill turn

`checkpoint.json` and `_author-context.md` are one artifact: the author lane's grill gate,
held once as a real conversation and frozen. A round seeds both before the author phase —
the gate file into the produced repo, the checkpoint into the run dir under a pinned
run id — and resumes from there. Because an `Await` checkpoint names the state it will
resume *into*, the first live state of the round is `refactor_backlog`, the state after the
gate. Everything from there is measured.

**Why this one turn is frozen, and nothing else is.** The rule is *freeze what the design
assigns to the operator; never freeze what the design assigns to the loop.* The grill gate
is the one gate of the author lane's twelve with no auto-resolver, deliberately: it asks the
product questions a backlog written at the level of observable behaviour leaves open, and
the design assigns them to a human by name. A human turn the product reserves for humans is
not part of the measured loop — it is the fixture's environment, and a benchmark that leaves
it live measures the human. (This is the opposite of seeding the OKF book, which *is* the
loop's output; seeding that would fake the work being measured.)

**What a score from this fixture does not cover.** The grill's question-generation turn no
longer runs per round, so the benchmark measures the loop **given a completed operator
turn** — it says nothing about the quality or the stability of the questions the grill asks.
That instability is excised here rather than solved, which is honest only while it is said
out loud. Say it anywhere a `grounded` number is quoted.

**The answers are not decided here.** Every answer in `_author-context.md` cites a standing
record under [`../docs/decisions/`](../docs/decisions/), which is where the decision lives
and where every lane's auto-resolver reads it. This file is a transcript, not a source.

**Editing it breaks the lineage.** The frozen artifacts *are* the fixture's identity: a
round is comparable only to rounds run against the same capture, and a comparison across
captures must say so out loud.
