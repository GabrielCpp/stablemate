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
that names a driver that does not exist. The same repo also gets a flat `docs/milestones/sample.md`,
a milestone filed as a single file instead of its own `<slug>/milestone.md` folder. The seed also
writes `doctor-ids-scratch/`, a repo of its own whose id registry holds a prefix of the wrong type.
Commands run there with `-C`, so no scenario sees these defects in the book of the checkout.

The seed also writes three books about outside systems under `doctor-scratch/docs/services/`. The
`resources` book holds four resource pages that each break one rule: a `reach:` that is neither
`http` nor `cli`, a probe that is an observation, an observation that is a POST, and a `base:` on
localhost. The `borrowing` book holds a valid resource and four fixtures that each break one rule: a
borrow without `lifetime: scenario`, a release with no borrow, a `request:` with an unknown method,
and a `run:` sent to an `http` resource. The `observing` book holds a cli page with three commands
that each break one rule: an `observe:` naming an observation the resource lacks, an `observe:` that
is not `@<resource>.<observation>`, and a `within=` on a row held on the response.

The seed also writes `doctor-register-scratch/`, a repo with an empty book whose artifacts dir
`doctor-register-scratch/art` holds a broken register. Record X-2 has no frontmatter. Record X-1
names decision D-9, which has no file. Decision D-1 cites X-1, which names another decision, and X-7,
which is on no shelf. Its commands run with `STABLEMATE_ARTIFACTS_DIR` set to that dir.

## Steps

### write-doctor-shell

- kind: seed
- run: mkdir -p doctor-scratch/docs/services/shell doctor-scratch/docs/services/shell/fixtures && printf -- '---\ntype: entries\nslug: entries\ntitle: shell\n---\n\n- \133Prepare](fixtures/prepare.md)\n' > doctor-scratch/docs/services/shell/entries.md && printf -- '---\ntype: fixture\nslug: prepare\ntitle: Prepare\n---\n# Prepare\n\nSeeds a file.\n\n## Steps\n\n### write-file\n\n- kind: seed\n- run: echo "unterminated\n' > doctor-scratch/docs/services/shell/fixtures/prepare.md

### write-doctor-launch

- kind: seed
- run: mkdir -p doctor-scratch/docs/services/launch doctor-scratch/docs/services/launch/fixtures doctor-scratch/docs/services/launch/screens && printf -- '---\ntype: entries\nslug: entries\ntitle: launch\n---\n\n- \133Prepare](fixtures/prepare-launch.md)\n- \133Home](screens/home.md)\n' > doctor-scratch/docs/services/launch/entries.md && printf -- '---\ntype: fixture\nslug: prepare-launch\ntitle: Prepare launch\n---\n# Prepare launch\n\nSeeds a file.\n\n- launch-screen: \133Home](../screens/home.md)\n\n## Steps\n\n### write-file\n\n- kind: seed\n- run: echo ok\n' > doctor-scratch/docs/services/launch/fixtures/prepare-launch.md && printf -- '---\ntype: screen\nslug: home\ntitle: Home\n---\n# Home\n\n- route: /\n' > doctor-scratch/docs/services/launch/screens/home.md

### write-doctor-ui

- kind: seed
- run: mkdir -p doctor-scratch/docs/services/ui doctor-scratch/docs/services/ui/screens && printf -- '---\ntype: entries\nslug: entries\ntitle: ui\n---\n\n- \133Home](screens/home.md)\n' > doctor-scratch/docs/services/ui/entries.md && printf -- '---\ntype: screen\nslug: home\ntitle: Home\n---\n# Home\n\n- route: /\n- requires:\n  - none\n- params:\n  - none\n- entry: opened directly at the root URL.\n\n## Screen states\n\n### loaded\n\n- shows: the heading\n\n## Components\n\n### rail\n\n- selector: `#rail`\n- role: navigation\n- name: the `Panels` label\n- placement: width 0-20%%, x 0-20%%\n- keyboard: Tab moves through the buttons.\n- parent: \133Home](#home)\n- verify: focusable(locator="#rail", activates="Press it")\n\n## Interactions\n\n### open-panel\n\n- on: \133Home](#home)\n- trigger: click\n- role: button\n- name: Open\n- keyboard: Enter opens the panel.\n- dialog: maybe\n' > doctor-scratch/docs/services/ui/screens/home.md

### write-doctor-milestone

- kind: seed
- run: mkdir -p doctor-scratch/docs/milestones && printf -- '---\ntype: milestone\ntitle: Sample\nstatus: proposed\n---\n# Sample\n' > doctor-scratch/docs/milestones/sample.md

### write-doctor-ops

- kind: seed
- run: mkdir -p doctor-scratch/docs/services/ops && printf -- '---\ntype: entries\nslug: entries\ntitle: ops\n---\n\n- \133Stack](stack.md)\n' > doctor-scratch/docs/services/ops/entries.md && printf -- '---\ntype: runbook\nslug: stack\ntitle: Stack\n---\n# Stack\n\n- driver: ftp\n' > doctor-scratch/docs/services/ops/stack.md

### write-doctor-ids

- kind: seed
- run: mkdir -p doctor-ids-scratch/.agents doctor-ids-scratch/art/epics doctor-ids-scratch/docs/services/demo && printf -- '{"prefix": 5}\n' > doctor-ids-scratch/.agents/ids.json && printf -- '---\ntype: entries\nslug: entries\ntitle: Demo\n---\n# Demo\n' > doctor-ids-scratch/docs/services/demo/entries.md

### write-doctor-register

- kind: seed
- run: mkdir -p doctor-register-scratch/.agents doctor-register-scratch/art/epics doctor-register-scratch/docs/services/demo doctor-register-scratch/art/backlogs/api-service/billing/X-1 doctor-register-scratch/art/backlogs/api-service/billing/X-2 doctor-register-scratch/art/adr && printf -- '{"prefix": "TST"}\n' > doctor-register-scratch/.agents/ids.json && printf -- '---\ntype: entries\nslug: entries\ntitle: Demo\n---\n# Demo\n' > doctor-register-scratch/docs/services/demo/entries.md && printf -- '---\nid: X-1\nrepo: api-service\narea: billing\npattern: untriaged\nfiled_by: person\nsummary: first item\ndecision: D-9\n---\n' > doctor-register-scratch/art/backlogs/api-service/billing/X-1/record.md && printf -- 'no frontmatter here\n' > doctor-register-scratch/art/backlogs/api-service/billing/X-2/record.md && printf -- '---\nid: D-1\ntitle: One retry policy\nstatus: proposed\nrepos:\n- api-service\nevidence:\n- X-1\n- X-7\n---\n\n## Context\n\n## Decision\n\n## Consequences\n' > doctor-register-scratch/art/adr/D-1.md

### write-doctor-resources

- kind: seed
- run: mkdir -p doctor-scratch/docs/services/resources && printf -- '---\ntype: entries\nslug: entries\ntitle: resources\n---\n\n- \133Reach](reach-ftp.md)\n- \133Probe](probe-kind.md)\n- \133Observation](observation-post.md)\n- \133Local](local-base.md)\n' > doctor-scratch/docs/services/resources/entries.md && printf -- '---\ntype: resource\ntitle: Reach ftp\n---\n# Reach ftp\n\n- reach: ftp\n- base: http://camera.example.internal:9000\n\n## Probe\n\n### answers\n\n- kind: probe\n- request: GET /health\n\n## Observations\n' > doctor-scratch/docs/services/resources/reach-ftp.md && printf -- '---\ntype: resource\ntitle: Probe kind\n---\n# Probe kind\n\n- reach: http\n- base: http://camera.example.internal:9000\n\n## Probe\n\n### answers\n\n- kind: observe\n- request: GET /health\n\n## Observations\n' > doctor-scratch/docs/services/resources/probe-kind.md && printf -- '---\ntype: resource\ntitle: Observation post\n---\n# Observation post\n\n- reach: http\n- base: http://camera.example.internal:9000\n\n## Probe\n\n### answers\n\n- kind: probe\n- request: GET /health\n\n## Observations\n\n### recordings\n\n- kind: observe\n- request: POST /recordings\n' > doctor-scratch/docs/services/resources/observation-post.md && printf -- '---\ntype: resource\ntitle: Local base\n---\n# Local base\n\n- reach: http\n- base: http://localhost:8080\n\n## Probe\n\n### answers\n\n- kind: probe\n- request: GET /health\n\n## Observations\n' > doctor-scratch/docs/services/resources/local-base.md

### write-doctor-borrowing

- kind: seed
- run: mkdir -p doctor-scratch/docs/services/borrowing doctor-scratch/docs/services/borrowing/fixtures doctor-scratch/docs/services/borrowing/resources && printf -- '---\ntype: entries\nslug: entries\ntitle: borrowing\n---\n\n- \133Camera](resources/camera.md)\n- \133No lifetime](fixtures/no-lifetime.md)\n- \133Release only](fixtures/release-only.md)\n- \133Bad request](fixtures/bad-request.md)\n- \133Mismatched](fixtures/mismatched.md)\n' > doctor-scratch/docs/services/borrowing/entries.md && printf -- '---\ntype: resource\ntitle: Camera\n---\n# Camera\n\n- reach: http\n- base: http://camera.example.internal:9000\n\n## Probe\n\n### answers\n\n- kind: probe\n- request: GET /health\n\n## Observations\n' > doctor-scratch/docs/services/borrowing/resources/camera.md && printf -- '---\ntype: fixture\ntitle: No lifetime\n---\n# No lifetime\n\nTakes the camera.\n\n- lifetime: run\n\n## Steps\n\n### take\n\n- kind: borrow\n- on: \133Camera](../resources/camera.md)\n- request: POST /leases\n' > doctor-scratch/docs/services/borrowing/fixtures/no-lifetime.md && printf -- '---\ntype: fixture\ntitle: Release only\n---\n# Release only\n\nTakes the camera.\n\n- lifetime: scenario\n\n## Steps\n\n### take\n\n- kind: release\n- on: \133Camera](../resources/camera.md)\n- request: DELETE /leases/1\n' > doctor-scratch/docs/services/borrowing/fixtures/release-only.md && printf -- '---\ntype: fixture\ntitle: Bad request\n---\n# Bad request\n\nTakes the camera.\n\n- lifetime: scenario\n\n## Steps\n\n### take\n\n- kind: borrow\n- on: \133Camera](../resources/camera.md)\n- request: FETCH /leases\n' > doctor-scratch/docs/services/borrowing/fixtures/bad-request.md && printf -- '---\ntype: fixture\ntitle: Mismatched\n---\n# Mismatched\n\nTakes the camera.\n\n- lifetime: scenario\n\n## Steps\n\n### take\n\n- kind: borrow\n- on: \133Camera](../resources/camera.md)\n- run: echo leased\n' > doctor-scratch/docs/services/borrowing/fixtures/mismatched.md

### write-doctor-observing

- kind: seed
- run: mkdir -p doctor-scratch/docs/services/observing doctor-scratch/docs/services/observing/resources && printf -- '---\ntype: entries\nslug: entries\ntitle: observing\n---\n\n- \133Lab app](cli.md)\n- \133Camera](resources/camera.md)\n' > doctor-scratch/docs/services/observing/entries.md && printf -- '---\ntype: resource\ntitle: Camera\n---\n# Camera\n\n- reach: http\n- base: http://camera.example.internal:9000\n\n## Probe\n\n### answers\n\n- kind: probe\n- request: GET /health\n\n## Observations\n\n### recordings\n\n- kind: observe\n- request: GET /recordings\n' > doctor-scratch/docs/services/observing/resources/camera.md && printf -- '---\ntype: cli\nslug: cli\ntitle: Lab app\n---\n# Lab app\n\nThe lab app.\n\n- binary: lab\n\n## Commands\n\n### nothing\n- usage: lab nothing\n- exits: 0 once the video plays\n- run: invoke(argv=\133"nothing"])\n- verify: exit_status(code=0)\n- observe: @camera.nothing\n- verify: count(subject="items", equals=1)\n### badref\n- usage: lab badref\n- exits: 0 once the video plays\n- run: invoke(argv=\133"badref"])\n- verify: exit_status(code=0)\n- observe: the camera recordings\n- verify: count(subject="items", equals=1)\n### offobs\n- usage: lab offobs\n- exits: 0 once the video plays\n- run: invoke(argv=\133"offobs"])\n- verify: exit_status(code=0)\n- verify: count(subject="items", equals=1, within=5)\n' > doctor-scratch/docs/services/observing/cli.md
