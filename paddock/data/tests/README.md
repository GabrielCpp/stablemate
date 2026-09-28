# tests

The tests for the properties every published paddock score rests on. They run with the harness's own tests under `make -C paddock test`.

## Map

- `_fixtures.py`: the frozen-app fixtures as a test sees them: task modules loaded the way `paddock.loader` loads them, and the apps that carry an answer key.
