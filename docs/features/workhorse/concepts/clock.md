---
type: concept
slug: clock
title: stablemate clock port
---
# stablemate clock port

The clock separates operator-readable wall time from monotonic elapsed time and waiting. Runtime
code receives the port so tests can advance time without sleeping; `SYSTEM_CLOCK` is the default
implementation backed by the operating system.

- code: `workhorse/workhorse/_vendor/stablemate_core/clock.py::Clock` @ca801af01944
- code: `workhorse/workhorse/_vendor/stablemate_core/clock.py::SystemClock` @ca801af01944
- code: `workhorse/workhorse/_vendor/stablemate_core/clock.py::SYSTEM_CLOCK` @ca801af01944

## Methods

### now
- sig: `now() -> datetime`
- abstract: true
- returns: the current wall-clock datetime
- verify: json_path(path="return", matches="^\\d{4}-\\d{2}-\\d{2} ")
- code: `workhorse/workhorse/_vendor/stablemate_core/clock.py::Clock.now` @ca801af01944

### monotonic
- sig: `monotonic() -> float`
- abstract: true
- returns: a non-decreasing monotonic timestamp for measuring durations
- verify: json_path(path="successive_returns.non_decreasing", equals=true)
- code: `workhorse/workhorse/_vendor/stablemate_core/clock.py::Clock.monotonic` @ca801af01944

### sleep
- sig: `sleep(seconds: float) -> None`
- abstract: true
- does: wait for the requested duration
- verify: json_path(path="elapsed_seconds", equals=1.5)
- returns: `None`
- verify: json_path(path="return_is_none", equals=true)
- code: `workhorse/workhorse/_vendor/stablemate_core/clock.py::Clock.sleep` @ca801af01944

### SystemClock.now
- sig: `now() -> datetime`
- returns: `datetime.now()` from the system clock
- verify: json_path(path="return", matches="^\\d{4}-\\d{2}-\\d{2} ")
- code: `workhorse/workhorse/_vendor/stablemate_core/clock.py::SystemClock.now` @ca801af01944

### SystemClock.monotonic
- sig: `monotonic() -> float`
- returns: `time.monotonic()` from the system clock
- verify: json_path(path="return", equals=1.5)
- code: `workhorse/workhorse/_vendor/stablemate_core/clock.py::SystemClock.monotonic` @ca801af01944

### SystemClock.sleep
- sig: `sleep(seconds: float) -> None`
- does: call the operating system sleep for `seconds`
- verify: count(subject="operating system sleep calls", equals=1)
- returns: `None`
- code: `workhorse/workhorse/_vendor/stablemate_core/clock.py::SystemClock.sleep` @ca801af01944
