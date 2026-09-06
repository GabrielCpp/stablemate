---
type: concept
slug: clock
title: stablemate clock port
---
# stablemate clock port

The clock separates operator-readable wall time from monotonic elapsed time and waiting. Runtime
code receives the port so tests can advance time without sleeping; `SYSTEM_CLOCK` is the default
implementation backed by the operating system.

- code: `workhorse/workhorse/_vendor/stablemate_core/clock.py::Clock`
- code: `workhorse/workhorse/_vendor/stablemate_core/clock.py::SystemClock`
- code: `workhorse/workhorse/_vendor/stablemate_core/clock.py::SYSTEM_CLOCK`

## Methods

### now
- sig: `now() -> datetime`
- abstract: true
- returns: the current wall-clock datetime
- code: `workhorse/workhorse/_vendor/stablemate_core/clock.py::Clock.now`

### monotonic
- sig: `monotonic() -> float`
- abstract: true
- returns: a non-decreasing monotonic timestamp for measuring durations
- code: `workhorse/workhorse/_vendor/stablemate_core/clock.py::Clock.monotonic`

### sleep
- sig: `sleep(seconds: float) -> None`
- abstract: true
- does: wait for the requested duration
- returns: `None`
- code: `workhorse/workhorse/_vendor/stablemate_core/clock.py::Clock.sleep`

### SystemClock.now
- sig: `now() -> datetime`
- returns: `datetime.now()` from the system clock
- code: `workhorse/workhorse/_vendor/stablemate_core/clock.py::SystemClock.now`

### SystemClock.monotonic
- sig: `monotonic() -> float`
- returns: `time.monotonic()` from the system clock
- code: `workhorse/workhorse/_vendor/stablemate_core/clock.py::SystemClock.monotonic`

### SystemClock.sleep
- sig: `sleep(seconds: float) -> None`
- does: call the operating system sleep for `seconds`
- verify: count(subject="operating system sleep calls", equals=1)
- returns: `None`
- code: `workhorse/workhorse/_vendor/stablemate_core/clock.py::SystemClock.sleep`
