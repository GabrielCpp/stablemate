# __PROGRAM_NAME__

**What this program is:** <one paragraph — the mechanism under test and why it could
make a network cheaper to train / run, in the standing-goal terms>.

**Strategic context:** <link to the roadmap / parent direction this serves>. This
directory is the **operational program**: a ladder of numerically-gated milestones,
one gate doc each.

**Binding context (read before any milestone):**
- `__CODE_ROOT__/CLAUDE.md` and the repo's research RULES doc (if present), skill `never-constraints` — the NEVER list.
- the repo's hardware/budget notes (if any) — the machine is the experimental subject.
- the relevant prior `findings/` — what is already ruled out and must not be repeated.

---

## North star

<2–4 sentences: the falsifiable end state. What capability, at what cost saving,
under what controls, that would make this program a success.>

---

## Single source of truth: the equivalence / success definition

State the one definition every gate reuses (exact-match? Δsteps vs scratch?). **Do
not redefine it per gate — link here.**

> **<Definition name>.** <the precise, measurable definition + the headline metric>.

---

## The four shared controls

Every gate runs the identical task/budget against these (instantiate all from one spec):

```text
scratch    — same architecture, random init, no injected knowledge
random     — injected slots filled with random vectors of matched norm/spectrum
shuffled   — correct injected content, assigned to the WRONG slots/keys
same-param — a dense model with the same trainable+active param budget
```

A result is **meaningful only if it beats `random` AND `shuffled`** (it used the
injected *content*, not just added capacity), and *interesting* only if it also
beats/ties `scratch`/`same-param` on the cost axis claimed.

---

## Shared metrics (report all; scored from raw output)

```text
<headline capability metric>     steps_to_threshold / walltime (reported)
trainable_params / active_params / loaded_params     generalization_gap
```

Plus the **zero-weights test** (zeroing trainable params must degrade output) on every gate.

---

## Anti-shortcut guards

<the leak / oracle / lookup checks specific to this program — descendants of the
prior kill criteria. Each gate must pass them or the verdict is FAIL.>

---

## Gate ladder

| Gate | Title | Depends on | Tests (one line) | Advancement criterion |
|------|-------|-----------|------------------|-----------------------|
| __GATE_ID__ | <title> | — | <what it tests> | <exact numeric gate> |

Each gate has its own doc (`__GATE_ID___<slug>.md`) with the exact thresholds.

---

## Program kill criteria

```text
- <condition under which the whole program is refuted and must hand off to the lead>
```

When a kill criterion fires, the verdict is **FAIL**, recorded as a negative-result
finding under `findings/` — never deleted, never softened.

---

## Experiment index

| Experiment file | Source | What it tests | Result |
|-----------------|--------|---------------|--------|
| `__CODE_ROOT__/experiments/<name>.py` | `original` | <one line> | *(not yet run)* |
