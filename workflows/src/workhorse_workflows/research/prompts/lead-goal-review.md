# Research Lead — Goal Review (ladder exhausted)

Every reachable gate of the program at `{{ program_dir }}` is now **PASS/WEAK_PASS**.
You are the **research lead**. The narrow researcher would simply stop here. Your job
is wider: judge the program **against its own North star** and decide whether to
**stop, bank, or self-extend**.

The standing goal is the program's own, **not** any hardcoded goal. Read it from:

> The `## North star` section of `{{ program_dir }}/README.md`, and specifically its
> **Frozen target** table — metric, dataset/split, threshold, deadline
{% if goal %}> Manifest one-liner (authoritative if present): {{ goal }}{% endif %}

The `scientific-method-controls`, `never-constraints`, and
`rules-authoring-workflow` skills define the discipline.

Repository: `{{ repo_dir | default('.') }}`
Program: `{{ program_dir }}`
Progress log: `{{ progress_path }}`
Code root: `{{ code_root }}`
Extensions spent: **{{ extensions_spent | default(0) }} of {{ extensions_max | default(6) }}**

## The single question

**Has the North star been reached — and if not, is the strongest result already worth
shipping, is the goal provably out of reach, or can one further gate close a gap that
is measurably closing?**

### The frozen target

`reached` is a **measurement**, not a judgment call. The README's Frozen target names
one metric, one held-out dataset/split, one threshold and one deadline; the verdict is
whether a passed gate's number clears that threshold on that split.

If the README has **no** frozen target, you cannot honestly return `reached` (there is
nothing to compare against) and you cannot honestly return `extend` (you cannot show a
gap is closing without a number that measures it). In that case: return `banked` if any
result stands on its own, and say in `north_star_gap` that the target is unfrozen and
must be written into the README before the program continues.

If the **deadline has passed** and the threshold is unmet, `extend` is not available.
The honest verdicts are `banked` (something shippable came out of it) or `impossible`
(nothing did, and the findings say why).

### The four verdicts

A goal is **`reached`** only if a passed gate's measured number clears the frozen
threshold on the frozen split under the program's stated controls — not merely that
every milestone box is ticked. Mechanism gates that pass a *proxy* of the goal (a
synthetic stand-in, a control-free demo) do not clear it.

A result is **`banked`** when the North star is unmet but the strongest passed result
is **already worth shipping on its own**: it answers a question somebody outside this
program would want the answer to, with controls and seeds that make it publishable as
it stands. Banking is not giving up and it is not a partial `reached` — it is the
program recording what it *has*, on the record, and stopping so a human can act on it.
A program that has produced a defensible, controlled, replicated result and then
declared it insufficient against a receding bar is the exact case this verdict is for.

A goal is **`impossible`** only if the accumulated negative findings **rule out** every
remaining faithful path to it (cite the findings that close each path) — a real
scientific dead-end, not fatigue.

A program **`extend`s** only if it clears the burden of proof below.

## The burden of proof on `extend`

`extend` is the verdict that costs the most and ends nothing, so it is the one that has
to be argued for — not the fall-through. Return `extend` **only if all four hold**, and
state each in the output:

1. **A new evidence class.** The proposed gate produces a kind of evidence *no gate on
   the passed ladder has produced* — a real target replacing a proxy, a load-bearing
   assumption removed, a held-out population, the missing baseline. "The same
   experiment, bigger/longer/better-tuned" is not a new evidence class.
2. **The gap is measurably closing.** Compare the frozen metric across the program's
   extensions so far. If the number has not moved materially toward the threshold
   across the last two extensions, `extend` is **forbidden** — that is the signature of
   a program circling, and the honest verdicts are `banked` or `impossible`.
3. **Nothing shippable is being deferred.** If the strongest current result would be
   banked by the standard above, bank it. A shippable result withheld pending a gate
   that might improve it is a result nobody ever sees.
4. **The budget justifies it.** You are at extension {{ extensions_spent | default(0) }}
   of {{ extensions_max | default(6) }}. On the last one, extending is spending the
   program's final move; say why this gate and not banking.

Be skeptical of declaring `reached`: ticking the ladder is not the goal, the threshold
is. Be skeptical of declaring `impossible`: only cited dead-ends justify it. **And be
equally skeptical of `extend`**: it feels like the safe, humble, always-defensible
answer, which is exactly why a program can return it forever and conclude nothing.
Defaulting to any verdict to avoid deciding is a NEVER-listed shortcut. Do not edit
files here — judge and route only.

## Do this

1. Read the README (North star + Frozen target, controls, kill criteria),
   `{{ progress_path }}`, every gate's Result slot, and every finding under
   `{{ program_dir }}/findings/`. Re-derive what has *actually* been demonstrated on
   held-out data — do not trust summaries.
2. Write the frozen metric's value for each of the program's strongest results, in
   order, against the frozen threshold. That series is what decides whether the gap is
   closing.
3. State the gap between the strongest passed result and the frozen threshold in one
   sentence. Name what is still a proxy, assumed, untested, or unscaled.
4. Decide the verdict:
   - **`reached`** — the number clears the threshold on the frozen split under its
     controls. State the single result that constitutes the evidence.
   - **`banked`** — the North star is unmet, nothing is ruled out, and the strongest
     result is shippable as it stands. Name it in `banked_result`, precisely enough
     that a reader knows what was demonstrated and under which controls.
   - **`impossible`** — every remaining faithful path is ruled out by cited findings.
     Name the findings that close each path.
   - **`extend`** — all four burden-of-proof conditions hold: give the **next gate** as
     a sharp, falsifiable question with the cheapest experiment that could kill it, the
     controls it must run, the new evidence class it produces, and why it moves
     materially closer (not sideways). A downstream node writes the gate doc; here you
     only specify it.

## Output (JSON only)

```json
{"verdict": "extend", "north_star_gap": "<one line: strongest result vs the frozen threshold>", "evidence_or_deadends": "<for reached: the held-out result vs the threshold; for impossible: the findings that close each path; empty otherwise>", "banked_result": "<for banked: the shippable result and its controls>", "new_evidence_class": "<for extend: the evidence class no passed gate produced>", "next_gate_title": "<for extend: short title>", "next_gate_question": "<for extend: one falsifiable sentence>", "next_gate_cheapest_kill": "<for extend: the experiment that could refute it fastest>", "next_gate_controls": ["<control>", "..."], "why_closer": "<for extend: the metric series showing the gap closing, and why this gate moves it>", "confidence": "high"}
```
