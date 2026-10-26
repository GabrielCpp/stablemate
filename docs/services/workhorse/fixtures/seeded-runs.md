---
type: fixture
title: Seeded runs
---
# Seeded runs

Run directories in every shape the operator commands refuse or read, under
`/tmp/workhorse-book/seeded`. No process serves any of them, so every `control` verb that needs
a live run reports the [liveness](../concepts/run-control.md) of the directory it names. The
[run directory](../concepts/run-directory.md) page describes each file seeded here.

- lifetime: lap
- code: `workhorse/workhorse/records.py::RunRecord` @0b6fbdc685b9

## Steps

### clear

- kind: seed
- run: rm -rf /tmp/workhorse-book/seeded

### make-dirs

- kind: seed
- run: mkdir -p /tmp/workhorse-book/seeded/finished /tmp/workhorse-book/seeded/failed-ghost /tmp/workhorse-book/seeded/contained /tmp/workhorse-book/seeded/no-line /tmp/workhorse-book/seeded/bare /tmp/workhorse-book/seeded/in-flight /tmp/workhorse-book/seeded/stale-pid /tmp/workhorse-book/seeded/yaml-era /tmp/workhorse-book/seeded/replay-run/turns/000-00001-x /tmp/workhorse-book/seeded/replay-run/turns/000-00002-noprompt /tmp/workhorse-book/seeded/replay-run/turns/000-00003-bad /tmp/workhorse-book/seeded/replay-run/turns/000-00004-moved

### finished

- kind: seed
- run: printf '%s' '{"terminal":"done"}' > /tmp/workhorse-book/seeded/finished/run.json && printf '%s' '{"engine":"pyflow","flow":"Main","state":"write","params":{"topic":"cats"}}' > /tmp/workhorse-book/seeded/finished/checkpoint.json

### failed-ghost

- kind: seed
- run: printf '%s' '{"terminal":"fail"}' > /tmp/workhorse-book/seeded/failed-ghost/run.json && printf '%s' '{"engine":"pyflow","flow":"Ghost","state":"draft"}' > /tmp/workhorse-book/seeded/failed-ghost/checkpoint.json

### contained

- kind: seed
- run: printf '%s' '{"terminal":"fail"}' > /tmp/workhorse-book/seeded/contained/run.json && printf '%s' '{"container":true,"resume_argv":["x"]}' > /tmp/workhorse-book/seeded/contained/launch.json

### no-line

- kind: seed
- run: printf '%s' '{"terminal":"fail"}' > /tmp/workhorse-book/seeded/no-line/run.json && printf '%s' '{}' > /tmp/workhorse-book/seeded/no-line/launch.json

### in-flight

- kind: seed
- run: printf '%s' '{}' > /tmp/workhorse-book/seeded/in-flight/run.json && printf '%s' '{"pid":999999}' > /tmp/workhorse-book/seeded/stale-pid/run.json

### yaml-era

- kind: seed
- run: printf '%s' '{"terminal":"fail"}' > /tmp/workhorse-book/seeded/yaml-era/run.json && printf '%s' '{"current_id":"n1"}' > /tmp/workhorse-book/seeded/yaml-era/checkpoint.json

### replay-turns

- kind: seed
- run: printf '%s' '{}' > /tmp/workhorse-book/seeded/replay-run/turns/000-00001-x/turn.json && printf '%s' 'hello' > /tmp/workhorse-book/seeded/replay-run/turns/000-00001-x/prompt.md && printf '%s' '{}' > /tmp/workhorse-book/seeded/replay-run/turns/000-00002-noprompt/turn.json && printf '%s' '{"timeout_scale":"x"}' > /tmp/workhorse-book/seeded/replay-run/turns/000-00003-bad/turn.json

### replay-moved

- kind: seed
- run: printf '%s' '{"start_trees":[{"path":"/tmp/workhorse-book/seeded/bare","head":"deadbeefdeadbeef"}]}' > /tmp/workhorse-book/seeded/replay-run/turns/000-00004-moved/turn.json && printf '%s' 'hello' > /tmp/workhorse-book/seeded/replay-run/turns/000-00004-moved/prompt.md

### variants

- kind: seed
- run: printf '%s' '0123456789' > /tmp/workhorse-book/seeded/v10.txt && printf '%s' '0123456789A' > /tmp/workhorse-book/seeded/v11.txt

### config

- kind: seed
- run: printf 'config_version = 2\n[profiles.cheap]\ncli = "claude"\n[profiles.odd]\ncli = "nope"\n[profiles.bare]\nmodel = "x"\n' > /tmp/workhorse-book/seeded/config.toml

### bad-json

- kind: seed
- run: printf '%s' '{' > /tmp/workhorse-book/seeded/bad-context.json && printf '%s' '[1]' > /tmp/workhorse-book/seeded/list-context.json && printf '%s' '[1]' > /tmp/workhorse-book/seeded/params-list.json

### landed

- kind: verify
- run: test -s /tmp/workhorse-book/seeded/config.toml && test -s /tmp/workhorse-book/seeded/replay-run/turns/000-00004-moved/prompt.md
