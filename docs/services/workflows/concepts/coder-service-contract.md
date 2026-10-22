---
type: concept
slug: coder-service-contract
title: Coder service contract
---
# Coder service contract

- code: `workflows/src/workhorse_workflows/coder/shared/contract.py::service_problems` @997bfb900763

The coder uses this contract at both sides of service setup: genesis validates the service it
leaves behind, while plan recording validates the service a plan intends to target. Both callers
pass the paths the repository's `services:` block declares. An empty list means the repository
declares no services, so declaration validation is skipped and the path only has to exist as a
directory.

The function reports all validation failures for its one service path as a list of human-readable
messages. It does not mutate the path or infer a service type.

## Methods

### service_problems

- sig: `service_problems(service_abs: Path, label: str, path: str = "", declared: Iterable[str] = ()) -> list[str]`
- does: returns one error identifying the label and absolute service path when the path does not exist
- verify: count(subject="service contract problems", equals=1)
- does: returns one error identifying the label when the path exists but is not a directory
- does: returns one error when services are declared and none declares `path`
- does: identifies the declaration error with the label and the declared paths
- verify: json_path(path="$[0]", matches=".*: path is not declared under `services:` in agents.yml \\(declared: .*\\)")
- does: skips declaration validation when no paths are declared
- verify: count(subject="service contract problems", equals=0)
- does: accepts the service when it is an existing directory and its path is one the repository declares
- returns: an empty list when every applicable service condition passes
- code: `workflows/src/workhorse_workflows/coder/shared/contract.py::service_problems` @997bfb900763
