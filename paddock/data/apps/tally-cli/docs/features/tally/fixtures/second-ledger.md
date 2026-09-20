---
type: fixture
title: Second ledger
---
# Second ledger

The working directory holds a second ledger file, `other.json`, that no command in this
scenario names with `--file`. [file](../tally.md#file)'s claim that two ledgers in one
directory never see each other only means something when a second one exists to leave
alone — without it, "unchanged" has nothing to check.

- provides:
  - path — the second ledger's file name
    - is: other.json

## Steps

### seed-second-ledger

- kind: seed
- run: sh -c 'printf "{\"currency\": \"USD\", \"entries\": []}" > other.json'
- working-directory: scenario:

### confirm-it-landed

- kind: verify
- run: test -f other.json
- working-directory: scenario:
