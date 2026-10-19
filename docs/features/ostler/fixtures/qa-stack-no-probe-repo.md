---
type: fixture
slug: qa-stack-no-probe-repo
title: qa stack no-probe repo
---
# qa stack no-probe repo

Seeds `qa-stack-scratch/`, a tiny book of its own under the checkout: one runbook whose only
service step launches an instant command and declares no `entry-url:`, so bring-up has nothing
to poll over HTTP and falls back to the launch command's own exit code.

## Steps

### write-qa-stack-runbook

- kind: seed
- run: mkdir -p qa-stack-scratch/docs/features/demo/ops && printf -- '---\ntype: runbook\ntitle: QA stack\n---\n# QA stack\n\n- driver: cli\n\n## Steps\n\n### serve\n\n- kind: service\n- run: true\n- health: true\n' > qa-stack-scratch/docs/features/demo/ops/qa-stack.md
