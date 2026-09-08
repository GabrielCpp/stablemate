---
type: concept
slug: coder-genesis-bootstrap-input-selection
title: Coder genesis bootstrap input selection
---
# Coder genesis bootstrap input selection

Genesis fields are cumulative configuration for one deterministic bootstrap path, not alternate
implementations. Supply each field whose concern applies to the target: repository identity and
service location (`target`, `service`, and `service_root`), Farrier configuration (`packs`,
`scaffolds`, `workflows`, and `assistants`), native stack setup (`init_cmd` and `marker`), and
service validation or gates (`markers` and `gates`). No field is a general replacement for another.

`markers` is the one source-defined compatibility choice: when it is empty, classification uses
the singular `marker`; when it is provided, it is the complete marker list. An existing repository
still receives configuration refresh, while an existing service skips native initialization, so
neither repository nor service state removes the need to supply the fields relevant to later
steps.

- code: `workflows/src/workhorse_workflows/coder/genesis/flow.py::Genesis`
- rule: supply the cumulative inputs required by the target and stack; use `markers` for an explicit complete marker list, otherwise use `marker` as its fallback
- detail: [coder genesis bootstrap concept selection](coder-genesis-bootstrap-concept-selection.md)
- detail: [coder genesis bootstrap guide](coder-genesis-bootstrap-guide.md)
- detail: [coder genesis bootstrap scope](coder-genesis-bootstrap-scope.md)
