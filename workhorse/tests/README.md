# tests

The workhorse test suite. Tests import their shared doubles from one module.

## Map

- `_fakes.py`: test doubles for the ports the runner is handed: backend, clock, telemetry and a stand-in groom.
