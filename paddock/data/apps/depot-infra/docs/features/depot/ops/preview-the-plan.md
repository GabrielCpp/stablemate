---
type: runbook
slug: preview-the-plan
title: Preview the depot's plan
---
# Preview the depot's plan

- driver: iac
- environment: [The depot stack](depot-stack.md)

Two commands, and the second one is the evidence. `make -C pulumi plan` writes the plan to
`pulumi/preview.json` rather than to a pipe, because a check that reads the plan and a person who
disagrees with it have to be looking at the same document.

The plan is taken against an empty backend, so every resource in it is a `create`. That is what
makes a count of the steps a statement about the program: a resource that has been deleted from the
program is simply not in the plan, and nothing else about the run looks different.

## Steps

### build-the-program
- kind: prepare
- run: `make -C pulumi build`
- verify: the program compiles against the pinned provider SDK before anything asks it for a plan

### plan
- kind: run
- run: `make -C pulumi plan`
- produces: pulumi/preview.json
- verify: `changeSummary.create` counts every resource the program declares, and `steps[]` carries
  each one's inputs as the program passes them
