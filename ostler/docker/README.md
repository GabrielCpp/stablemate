# docker

The container images ostler runs QA scenarios in. The build context is the `ostler/` package directory.

## Map

- `sandbox/`: the QA sandbox image, which holds an interpreter and the harness and nothing a scenario could rerun a unit suite with.
