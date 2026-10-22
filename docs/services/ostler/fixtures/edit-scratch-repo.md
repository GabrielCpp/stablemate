---
type: fixture
slug: edit-scratch-repo
title: edit scratch repo
---
# edit scratch repo

Seeds `edit-scratch/`, a small repo of its own under the checkout that the editing commands act on. It
holds one epic with a story `sx` and a review resolution that declines its one finding. It holds a
`demo` service with a `cli` page, an `api` page whose endpoint cites its test in a `verify:` bullet, a
`tidy` page with out-of-order frontmatter and a wikilink, an `idea` page beside the others instead of
under `concepts/`, a `server` page with two endpoints and an invocation, and a `ledger` page past the
page size limit. A feature page `area/rec.md` is linked from the story. Commands run there with
`-C edit-scratch` and an artifacts directory inside it, so no run writes into the artifacts directory
of the person running the book.

## Steps

### write-edit-ids

- kind: seed
- run: mkdir -p edit-scratch/.agents && printf -- '{\n  "prefix": "TST"\n}\n' > edit-scratch/.agents/ids.json

### write-edit-story

- kind: seed
- run: mkdir -p edit-scratch/art/specs/TST-01M585PFWZZXH4Y6KNMH1VK58H edit-scratch/docs/epics/0001-first edit-scratch/docs/epics/0001-first/stories/sx edit-scratch/docs/services/area && printf -- '---\ntype: epic\nid: TST-01M585PEGMRE3FWETV74QRSSY3\ntitle: First epic\nstatus: planned\n---\n# Epic: First epic\n\n## Seeds\n\n## Stories\n\n### sx\n- title: Story sx\n- id: TST-01M585PFWZZXH4Y6KNMH1VK58H\n- covers: (none)\n' > edit-scratch/docs/epics/0001-first/epic.md && printf -- '---\ntype: story\nid: TST-01M585PFWZZXH4Y6KNMH1VK58H\nslug: sx\nstatus: Not started\n---\n# Story: Story sx\n\n## Dependencies\n\n(none)\n\n## Fixtures\n\n(none)\n\n## Context\n\nThe record lives in \133the record](../../../../services/area/rec.md).\n\n## Acceptance Criteria\n\n## Non-Functional Acceptance Criteria\n\n## Technical Notes\n\n## Implementation Status\n\n- **Status**: Not started\n' > edit-scratch/docs/epics/0001-first/stories/sx/story.md && printf -- '{\n  "status": "applied",\n  "findings": \133\n    {\n      "id": "Finding 1",\n      "disposition": "declined",\n      "reason": "out of scope for this story"\n    }\n  ]\n}\n' > edit-scratch/art/specs/TST-01M585PFWZZXH4Y6KNMH1VK58H/review-resolution.json && printf -- '---\ntype: concept\nslug: rec\ntitle: Record\n---\n# Record\n\nA record of the area.\n' > edit-scratch/docs/services/area/rec.md

### write-edit-book

- kind: seed
- run: mkdir -p edit-scratch/docs/services/demo edit-scratch/docs/services/demo/http edit-scratch/src && printf -- '---\ntype: cli\nslug: cli\ntitle: demo\n---\n# demo\n\n- binary: demo\n- code: src/demo.py::greet\n\n## Commands\n\n### demo-greet\n- usage: demo greet\n- exits: 0 always\n- run: invoke(argv=\133"greet"])\n- verify: exit_status(code=0)\n- fixture: none, because nothing is seeded\n- code: src/demo.py::greet\n\n- see \133the idea](idea.md)\n' > edit-scratch/docs/services/demo/cli.md && printf -- '---\ntitle: Tidy\ntype: concept\nslug: tidy\n---\n# Tidy\n\nSee \133\133rec]] for the record.\n' > edit-scratch/docs/services/demo/tidy.md && printf -- '---\ntype: api\nslug: api\ntitle: Api\n---\n# Api\n\n## Endpoints\n\n### submit\n- method: POST\n- path: /x\n- verify: `src/test_demo.py::test_submit`\n' > edit-scratch/docs/services/demo/api.md && printf -- '---\ntype: entries\nslug: entries\ntitle: demo\n---\n\n- \133demo](cli.md)\n- \133Tidy](tidy.md)\n- \133Api](api.md)\n- \133Idea](idea.md)\n- \133Demo API](http/server.md)\n- \133Ledger](concepts/ledger.md)\n' > edit-scratch/docs/services/demo/entries.md && printf -- '---\ntype: concept\nslug: idea\ntitle: Idea\n---\n# Idea\n\nAn idea.\n' > edit-scratch/docs/services/demo/idea.md && printf -- 'def greet():\n    return "hi"\n' > edit-scratch/src/demo.py && printf -- '---\ntype: server\ntitle: Demo API\n---\n# Demo API\n\n- entry-url: http://localhost:8000\n- code: `src/demo.py`\n\n## Endpoints\n\n### get-widget\n\n- method: GET\n- path: /widgets/{id}\n- status: 200\n- verify: http_status(code=200, path="/widgets/1")\n\n### create-widget\n\n- method: POST\n- path: /widgets\n- status: 201\n\n## Invocations\n\n### fetch-widget\n\n- on: \133get-widget](#get-widget)\n- trigger: the home screen loads\n' > edit-scratch/docs/services/demo/http/server.md

### write-edit-ledger

- kind: seed
- run: mkdir -p edit-scratch/docs/services/demo/concepts && { printf -- '---\ntype: concept\nslug: ledger\ntitle: Ledger\n---\n# Ledger\n\n## Rules\n\nEvery rule.\n\n'; for n in 1 2 3 4 5 6 7 8 9; do printf -- '### rule-%s\n\n- rule: entries obey rule %s\n\n' $n $n; yes 'The ledger keeps this rule for every entry it records, whichever account the entry lands in.' | head -n 90; printf '\n'; done; printf '## Notes\n\nAppend only.\n'; } > edit-scratch/docs/services/demo/concepts/ledger.md
