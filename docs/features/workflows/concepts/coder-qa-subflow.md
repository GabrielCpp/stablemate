---
type: concept
slug: coder-qa-subflow
title: Coder QA subflow
---
# Coder QA subflow

The Coder QA subflow is the package-owned implementation behind the [Coder QA flow](../flows/coder-qa.md).
Its public entry is `Qa`; the package initializer exposes that flow while keeping the
implementation groups below private to this subflow.

The `qa` node group owns evidence cleanup, stack lifecycle, QA-plan linting and validation,
dry-run proof, secret minting, and execution of the scored QA plan. The `evidence` group
validates runner artifacts and refuses a claimed pass when its proof is missing, contradictory,
stale, or rests on a failed scenario. The `regression` group discovers journey commands from
the touched services and classifies each execution as passed, failed, blocked, skipped, or
error. The `hygiene` group relocates untracked root screenshots and rejects sentinel IDs or
unreconciled placeholders in added shipped source.

The groups are deliberately separate bounded contracts: lifecycle operations translate the
book and runner outcomes, evidence is the fail-closed proof gate, regression owns [committed
journey suites](coder-qa-regression.md), and [hygiene](qa-hygiene-gates.md) performs deterministic
pre-commit checks. The flow composes them;
the package does not expose a second public surface for these nodes.

- code: `workflows/src/workhorse_workflows/coder/qa/__init__.py::__all__`
- detail: [QA evidence gate](qa-evidence-gate.md)
- detail: [QA hygiene gates](qa-hygiene-gates.md)
