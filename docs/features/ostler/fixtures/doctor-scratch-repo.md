---
type: fixture
slug: doctor-scratch-repo
title: doctor scratch repo
---
# doctor scratch repo

Seeds `doctor-scratch/`, a repo of its own under the checkout that holds four small books, each with
one kind of defect for `ostler doctor` to report. The `shell` book has a fixture step that is not a
shell command. The `launch` book has a fixture that names a launch screen the screen's own page does
not support. The `ui` book has a screen that names its component with a description, checks a key no
browser can press, and answers a dialog with neither accept nor dismiss. The `ops` book has a runbook
that names a driver that does not exist. The seed also writes `doctor-ids-scratch/`, a repo of its
own whose id registry holds a prefix of the wrong type. Commands run there with `-C`, so no scenario
sees these defects in the book of the checkout.

## Steps

### write-doctor-shell

- kind: seed
- run: mkdir -p doctor-scratch/docs/features/shell doctor-scratch/docs/features/shell/fixtures && printf -- '---\ntype: entries\nslug: entries\ntitle: shell\n---\n\n- \133Prepare](fixtures/prepare.md)\n' > doctor-scratch/docs/features/shell/entries.md && printf -- '---\ntype: fixture\nslug: prepare\ntitle: Prepare\n---\n# Prepare\n\nSeeds a file.\n\n## Steps\n\n### write-file\n\n- kind: seed\n- run: echo "unterminated\n' > doctor-scratch/docs/features/shell/fixtures/prepare.md

### write-doctor-launch

- kind: seed
- run: mkdir -p doctor-scratch/docs/features/launch doctor-scratch/docs/features/launch/fixtures doctor-scratch/docs/features/launch/screens && printf -- '---\ntype: entries\nslug: entries\ntitle: launch\n---\n\n- \133Prepare](fixtures/prepare.md)\n- \133Home](screens/home.md)\n' > doctor-scratch/docs/features/launch/entries.md && printf -- '---\ntype: fixture\nslug: prepare-launch\ntitle: Prepare launch\n---\n# Prepare launch\n\nSeeds a file.\n\n- launch-screen: \133Home](../screens/home.md)\n\n## Steps\n\n### write-file\n\n- kind: seed\n- run: echo ok\n' > doctor-scratch/docs/features/launch/fixtures/prepare.md && printf -- '---\ntype: screen\nslug: home\ntitle: Home\n---\n# Home\n\n- route: /\n' > doctor-scratch/docs/features/launch/screens/home.md

### write-doctor-ui

- kind: seed
- run: mkdir -p doctor-scratch/docs/features/ui doctor-scratch/docs/features/ui/screens && printf -- '---\ntype: entries\nslug: entries\ntitle: ui\n---\n\n- \133Home](screens/home.md)\n' > doctor-scratch/docs/features/ui/entries.md && printf -- '---\ntype: screen\nslug: home\ntitle: Home\n---\n# Home\n\n- route: /\n- requires:\n  - none\n- params:\n  - none\n- entry: opened directly at the root URL.\n\n## Screen states\n\n### loaded\n\n- shows: the heading\n\n## Components\n\n### rail\n\n- selector: `#rail`\n- role: navigation\n- name: the `Panels` label\n- placement: width 0-20%%, x 0-20%%\n- keyboard: Tab moves through the buttons.\n- parent: \133Home](#home)\n- verify: focusable(locator="#rail", activates="Press it")\n\n## Interactions\n\n### open-panel\n\n- on: \133Home](#home)\n- trigger: click\n- role: button\n- name: Open\n- keyboard: Enter opens the panel.\n- dialog: maybe\n' > doctor-scratch/docs/features/ui/screens/home.md

### write-doctor-ops

- kind: seed
- run: mkdir -p doctor-scratch/docs/features/ops && printf -- '---\ntype: entries\nslug: entries\ntitle: ops\n---\n\n- \133Stack](stack.md)\n' > doctor-scratch/docs/features/ops/entries.md && printf -- '---\ntype: runbook\nslug: stack\ntitle: Stack\n---\n# Stack\n\n- driver: ftp\n' > doctor-scratch/docs/features/ops/stack.md

### write-doctor-ids

- kind: seed
- run: mkdir -p doctor-ids-scratch/.agents doctor-ids-scratch/docs/epics doctor-ids-scratch/docs/features/demo && printf -- '{"prefix": 5}\n' > doctor-ids-scratch/.agents/ids.json && printf -- '---\ntype: entries\nslug: entries\ntitle: Demo\n---\n# Demo\n' > doctor-ids-scratch/docs/features/demo/entries.md
