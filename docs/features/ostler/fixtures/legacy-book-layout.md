---
type: fixture
slug: legacy-book-layout
title: legacy book layout
---
# legacy book layout

Seeds a `docs/` tree in the legacy pre-OKF layout under `okf-migrate-fixture/`: one epic with a
`seed.json` and a `dependencies.json` sibling instead of frontmatter, an `epics-todo.json` queue
naming that epic, and a feature page with no `type:` frontmatter at all.

## Steps

### seed-legacy-epic

- kind: seed
- run: mkdir -p okf-migrate-fixture/docs/epics/sample-epic && printf '# Sample Epic\n\nA narrative paragraph.\n' > okf-migrate-fixture/docs/epics/sample-epic/epic.md

### seed-legacy-epic-seed-json

- kind: seed
- run: printf '%s' '{"epicId":"sample-epic","items":[{"id":"SEED-1","status":"backlog","summary":"do the thing"}]}' > okf-migrate-fixture/docs/epics/sample-epic/seed.json

### seed-legacy-epic-dependencies-json

- kind: seed
- run: printf '%s' '{"epicId":"sample-epic","epicTitle":"Sample Epic","stories":[{"slug":"story-one","title":"Story One","seedItems":["SEED-1"],"dependencies":[]}]}' > okf-migrate-fixture/docs/epics/sample-epic/dependencies.json

### seed-legacy-todo

- kind: seed
- run: printf '%s' '["sample-epic"]' > okf-migrate-fixture/docs/epics/epics-todo.json

### seed-legacy-feature

- kind: seed
- run: mkdir -p okf-migrate-fixture/docs/features && printf '# Legacy Page\n\nSome text.\n' > okf-migrate-fixture/docs/features/legacy-page.md
