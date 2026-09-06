---
type: concept
slug: workflow-kit-telemetry
title: Workflow kit telemetry
---
# Workflow kit telemetry

`workhorse_workflows.kit.telemetry` shapes checkpoint state values into low-cardinality span
labels. Counter labels include only named integer values and exclude booleans; verdict labels
include only named, non-empty strings. Both label helpers use a caller-supplied prefix, so a
workflow can distinguish its dimensions without changing the source field names. The progress
classifier compares finding identities rather than only counts, preserving the distinction
between a pass that changed nothing and one that closed findings while opening replacements.

- code: `workflows/src/workhorse_workflows/kit/telemetry.py`

## Fields

### ProgressVerdict

- type: `Literal["cleared", "first_pass", "reduced", "regressed", "stalled", "churned"]`
- semantics: the closed vocabulary accepted for a progress verdict span label
- code: `workflows/src/workhorse_workflows/kit/telemetry.py::ProgressVerdict`

## Methods

### counter_labels

- sig: `counter_labels(source: Mapping[str, Any], prefix: str, names: Sequence[str]) -> dict[str, str]`
- does: emits one label named `{prefix}.{name}` for each requested source value that is an integer
- verify: count(subject="integer counter labels emitted", equals=2)
- does: stringifies each emitted integer value
- verify: count(subject="stringified counter label values", equals=2)
- does: omits requested names whose values are absent, non-integer, or boolean
- verify: absent(subject="counter label for an omitted non-integer value")
- returns: returns a dictionary containing only the emitted prefixed counter labels
- verify: count(subject="returned counter label entries", equals=2)
- code: `workflows/src/workhorse_workflows/kit/telemetry.py::counter_labels`
- tests: `workflows/tests/coder/test_telemetry.py::test_counters_are_prefixed_and_stringified`
- tests: `workflows/tests/coder/test_telemetry.py::test_a_counter_the_state_does_not_carry_is_absent_not_zero`
- tests: `workflows/tests/coder/test_telemetry.py::test_a_bool_is_not_an_attempt_count`

### verdict_labels

- sig: `verdict_labels(source: Mapping[str, Any], prefix: str, names: Sequence[str]) -> dict[str, str]`
- does: emits one label named `{prefix}.{name}` for each requested source value that is a non-empty string
- verify: count(subject="non-empty verdict labels emitted", equals=1)
- does: omits requested names whose values are absent, non-string, or empty
- verify: absent(subject="verdict label for an empty value")
- returns: returns a dictionary containing only the emitted prefixed verdict labels
- verify: count(subject="returned verdict label entries", equals=1)
- code: `workflows/src/workhorse_workflows/kit/telemetry.py::verdict_labels`
- tests: `workflows/tests/coder/test_telemetry.py::test_verdicts_skip_the_gate_that_has_not_run`
- tests: `workflows/tests/coder/test_telemetry.py::test_a_recorded_verdict_reaches_the_labels`

### progress_verdict

- sig: `progress_verdict(previous: Sequence[str] | None, current: Sequence[str]) -> ProgressVerdict`
- does: returns `cleared` when the current finding identity set is empty
- verify: count(subject="cleared progress verdicts", equals=1)
- does: returns `first_pass` when the current set is non-empty and there is no prior failing set
- verify: count(subject="first-pass progress verdicts", equals=1)
- does: returns `reduced` when the current set has fewer identities than the prior failing set
- verify: count(subject="reduced progress verdicts", equals=1)
- does: returns `regressed` when the current set has more identities than the prior failing set
- verify: count(subject="regressed progress verdicts", equals=1)
- does: returns `stalled` when the current and prior sets contain the same identities
- verify: count(subject="stalled progress verdicts", equals=1)
- does: returns `churned` when both sets have the same size but contain different identities
- verify: count(subject="churned progress verdicts", equals=1)
- does: compares unique finding identities as sets, so duplicate entries do not affect classification
- verify: count(subject="identity-set progress classifications", equals=1)
- returns: returns exactly one member of the `ProgressVerdict` vocabulary
- verify: count(subject="closed progress verdict vocabulary", equals=6)
- code: `workflows/src/workhorse_workflows/kit/telemetry.py::progress_verdict`
- tests: `workflows/tests/coder/test_telemetry.py::test_progress_verdict_names_what_a_pass_bought`
- tests: `workflows/tests/coder/test_telemetry.py::test_a_pass_that_closed_two_and_opened_two_is_not_a_stall`
- tests: `workflows/tests/coder/test_telemetry.py::test_an_empty_baseline_is_a_first_pass_not_a_reduction`
