---
type: fixture
title: Expenses CSV
---
# Expenses CSV

The working directory holds `expenses.csv`, a well-formed file the ledger has not seen, so
`import` has something new to add. The two rows total `7100` cents — added to `add`'s own
`350`, `report`'s claimed total of `7450` holds only because this fixture put them there.

The commands are named here rather than linked: this page sits in the tree at every story's
epoch, while `tally.md` is pinned to the book as it stood for that story, so a link forward to
a command a story has not written yet resolves against a heading that is not there. What binds
this fixture to the commands that need it is their own `fixture:` bullet, not a prose link.

- provides:
  - path — the CSV file's name
    - is: expenses.csv

## Steps

### seed-expenses-csv

- kind: seed
- run: sh -c 'printf "who,what,amount_cents,spent_on\nbob,dinner,4600,2024-01-02\ncarol,taxi,2500,2024-01-03\n" > expenses.csv'
- working-directory: .

### confirm-it-landed

- kind: verify
- run: test -f expenses.csv
- working-directory: .
