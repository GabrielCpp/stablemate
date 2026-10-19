---
type: fixture
slug: qa-web-journey-repo
title: qa web journey repo
---
# qa web journey repo

Seeds `qa-web-scratch/`, a small git repository of its own under the checkout, separate from
[the qa scratch repo](qa-scratch-repo.md). It holds a one-screen book for a `demo` web surface: a
runbook that declares `driver: web` and an `entry-url:`, a screen with one component, one state and
one interaction, and a flow that walks the interaction into the state. One commit holds the book,
then `src/frontend.py`, the file the interaction and the state cite, changes without a commit, so a
packet built against it owes both nodes live evidence and the flow they sit on. Commands run there
with `-C qa-web-scratch` and with `STABLEMATE_ARTIFACTS_DIR` pointed at the scratch tree, so no spec
reaches the artifacts directory of the person who runs the book.

## Steps

### write-qa-web-book

- kind: seed
- run: mkdir -p qa-web-scratch/art/specs/s1 qa-web-scratch/docs/features/demo/screens qa-web-scratch/docs/features/demo/ops qa-web-scratch/docs/features/demo/flows qa-web-scratch/src && printf -- 'art/\nrepo.git/\n' > qa-web-scratch/.gitignore && printf -- '---\ntype: entries\nslug: entries\ntitle: demo\n---\n\n- \133Home](screens/home.md)\n- \133Stack](ops/stack.md)\n- \133Open the panel](flows/open-the-panel.md)\n' > qa-web-scratch/docs/features/demo/entries.md && printf -- '---\ntype: runbook\nslug: stack\ntitle: Stack\n---\n# Stack\n\n- driver: web\n- entry-url: http://localhost:4100\n- surfaces:\n  - \133Home](../screens/home.md)\n\n## Steps\n\n### serve\n\n- kind: service\n- run: true\n- health: true\n' > qa-web-scratch/docs/features/demo/ops/stack.md && printf -- '---\ntype: screen\nslug: home\ntitle: Home\n---\n# Home\n\n- route: /\n- requires:\n  - none\n- params:\n  - none\n- entry: opened directly at the root URL.\n\n## Components\n\n### open-button\n\n- role: button\n- name: Open\n- placement: width 0-20%%, x 0-20%%\n- keyboard: Enter activates it.\n- parent: \133Home](#home)\n\n## Screen states\n\n### opened\n\n- shows: \133Open button](#open-button)\n- code: src/frontend.py::render_opened@aaaaaaaaaaaa\n- fixture: none, because the screen settles in that state as it opens\n\n## Interactions\n\n### click-open\n\n- on: \133Open button](#open-button)\n- trigger: click\n- role: button\n- name: Open\n- keyboard: Enter activates it.\n- does:\n  - opens the panel\n- code: src/frontend.py::handle_click@bbbbbbbbbbbb\n' > qa-web-scratch/docs/features/demo/screens/home.md && printf -- '---\ntype: flow\nslug: open-the-panel\ntitle: Open the panel\n---\n# Open the panel\n\n- start: the home screen is open\n- steps:\n  - \133Click open](../screens/home.md#click-open)\n  - \133Opened](../screens/home.md#opened)\n- end: \133the opened state](../screens/home.md#opened) shows the panel\n- verify: visible(locator="../screens/home.md#open-button")\n- fixture: none, because nothing is seeded\n' > qa-web-scratch/docs/features/demo/flows/open-the-panel.md && printf -- 'def render_opened():\n    return "<div>open</div>"\n\n\ndef handle_click():\n    return "opened"\n' > qa-web-scratch/src/frontend.py && printf -- 'from ostler_qa import Qa, plan, scenario, target\n\nplan(run_id="qa-web-s1", story="s1")\n' > qa-web-scratch/art/specs/s1/qa_plan.py

### commit-qa-web-base

- kind: seed
- run: cd qa-web-scratch && export GIT_DIR=repo.git GIT_WORK_TREE=. && git init -q && git config --unset core.worktree && unset GIT_WORK_TREE && git add -A && git -c user.name=okf -c user.email=okf@example.com commit -q -m base

### change-qa-web-source

- kind: seed
- run: mkdir -p qa-web-scratch/src && printf -- 'def render_opened():\n    return "<div class=\"open\">open</div>"\n\n\ndef handle_click():\n    return "opened"\n' > qa-web-scratch/src/frontend.py
