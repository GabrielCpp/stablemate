---
type: concept
slug: okf-builder-command-selection
title: OKF-builder command selection
---
# OKF-builder command selection

`workflows/src/workhorse_workflows/okf_builder/workflow.py::main` creates the console-script
handler from the registry's entry point. The same registry binds the default OKF-builder flow and
the named `audit` and `walkthrough-web` flows, so its commands are complementary operations on
one workflow surface rather than alternate implementations of a single operation.

Use `run` to start the default builder or a selected registered flow, `dot` to render the
registered builder and walkthrough state graphs, and `version` to report the installed Workhorse
engine version. All three commands are current; none is preferred or deprecated because each
answers a distinct operational need.

- code: `workflows/src/workhorse_workflows/okf_builder/workflow.py::main`
- rule: select `run` for flow execution, `dot` for state-graph rendering, and `version` for installed-engine identification; no command supersedes another
