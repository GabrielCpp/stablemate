# __GATE_ID__ — <Gate Title>

**Status:** NOT STARTED
**Date:** —
**Part of:** [__PROGRAM_NAME__](README.md)
**Depends on:** <upstream gates, or — for the first>
**Blocks:** <downstream gates>

## 1. Why this comes first / where it sits

<one paragraph: the question this gate answers and why it must pass before the next>

## 2. Hypothesis

<one falsifiable sentence>

## 3. Design / deliverables

<what gets built and measured — the experiment, not the implementation detail. Name
the controls from the program README that this gate runs.>

## 4. Success gate (exact numeric thresholds)

```text
<metric> <op> <threshold>   AND   beats random/shuffled   AND   zero-weights degrades
```

Map to PASS / WEAK_PASS / FAIL per `scientific-method-controls`.

## 5. Failure modes to watch

<the anti-shortcut traps specific to this gate>

## 6. Baseline / imports

<what to reuse from src — the measurement harness, control factory, etc.>

## 7. Result slot

**Date:** —
**Metrics:** <mean±std per metric over seeds, deltas vs each control — filled after running>
