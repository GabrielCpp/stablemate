---
type: format
slug: pm-ledger
title: PM ledger
---
# PM ledger

The PM ledger is `grills/pm.md` beside the approved milestone. Every product question the product manager or the operator answered during an Author run is appended to it, in order, and it only ever grows. Every writer and reviewer prompt includes it, so an answer binds all later turns.

The operator may edit the file. An entry the operator changes or adds overrules whatever the product manager decided before.

- file: `<milestone directory>/grills/pm.md`
- code: `workflows/src/workhorse_workflows/author/pm/ledger.py::append_entry` @84430f7ef63f
- code: `workflows/src/workhorse_workflows/author/pm/ledger.py::ledger_entry` @84430f7ef63f
- code: `workflows/src/workhorse_workflows/author/pm/ledger.py::HEADING` @84430f7ef63f
- detail: [Author PM gap answer](../concepts/author-pm-gap-answer.md)

## Fields

### asker
- type: string
- required: true
- semantics: the entry's `##` heading, the stage that asked
- verify: contents(subject="grills/pm.md", matches="(?m)^## epic-split$")
- code: `workflows/src/workhorse_workflows/author/pm/ledger.py::ledger_entry` @84430f7ef63f

### answered by
- type: literal `pm` or `human`
- required: true
- semantics: who settled the question
- verify: contents(subject="grills/pm.md", matches="Answered by\\*\\*: (pm|human)")
- code: `workflows/src/workhorse_workflows/author/pm/ledger.py::ledger_entry` @84430f7ef63f

### question and answer
- type: markdown
- required: true
- semantics: the writer's question and the decision, each under its own bold label
- verify: contents(subject="grills/pm.md", matches="\\*\\*Answer\\*\\*")
- code: `workflows/src/workhorse_workflows/author/pm/ledger.py::ledger_entry` @84430f7ef63f
