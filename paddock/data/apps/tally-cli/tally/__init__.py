"""tally — a shared-expense ledger kept in one JSON file.

The package is deliberately import-only: every command is a function in `tally.cli`, and the
process boundary lives in `tally.__main__`. A test imports what it wants to exercise rather
than shelling out, and the CLI is the same code path either way.
"""
