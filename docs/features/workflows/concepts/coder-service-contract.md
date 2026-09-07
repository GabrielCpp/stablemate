---
type: concept
slug: coder-service-contract
title: Coder service contract
---
# Coder service contract

- code: `workflows/src/workhorse_workflows/coder/shared/contract.py::service_problems`

The coder uses this contract at both sides of service setup: genesis validates the service it
leaves behind, while plan recording validates the service a plan intends to target. Both callers
pass the configured marker sequence through unchanged. An empty marker sequence means the
repository has not declared a marker policy, so marker validation is skipped rather than replaced
with stack-specific defaults.

The function reports all validation failures for its one service path as a list of human-readable
messages. It does not mutate the path or infer a service type.

## Methods

### service_problems

- sig: `service_problems(service_abs: Path, markers: Sequence[str], label: str) -> list[str]`
- does: returns one error identifying the label and absolute service path when the path does not exist
- verify: count(subject="service contract problems", equals=1)
- does: returns one error identifying the label when the path exists but is not a directory
- verify: count(subject="service contract problems", equals=1)
- does: returns one error when markers are configured and none exists below the service directory
- verify: count(subject="service contract problems", equals=1)
- does: identifies the marker error with the label, expected marker names, and service path
- verify: json_path(path="$[0]", matches=".*: no service marker found \\(expected one of \\[.*\\] in .+\\)")
- does: skips marker validation when the marker sequence is empty
- verify: count(subject="service contract problems", equals=0)
- does: accepts the service when it is an existing directory and at least one configured marker exists below it
- verify: count(subject="service contract problems", equals=0)
- returns: an empty list when every applicable service condition passes
- verify: count(subject="service contract problems", equals=0)
- code: `workflows/src/workhorse_workflows/coder/shared/contract.py::service_problems`
