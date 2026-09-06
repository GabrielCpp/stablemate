---
type: concept
slug: runtime-clock
title: Runtime clock
---
# Runtime clock

Time-dependent code receives a clock contract instead of reading or waiting on ambient time.
Wall-clock dates are for operator-visible timestamps; monotonic seconds measure elapsed deadlines,
and sleeping is the only operation that waits. The vendored core module defines the contract and
its system-backed implementation; Farrier carries the module even though no Farrier module calls
it directly.

- code: `farrier/farrier/_vendor/stablemate_core/clock.py::Clock`
- code: `farrier/farrier/_vendor/stablemate_core/clock.py::SystemClock`
- code: `farrier/farrier/_vendor/stablemate_core/clock.py::SYSTEM_CLOCK`
- detail: [farrier CLI](../farrier.md)

## Methods

### method: now
- sig: `now() -> datetime`
- abstract: true
- does: returns the current wall-clock date and time
- returns: a `datetime` suitable for operator-visible timestamps
- verify: json_path(path="return value", matches="^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]+)?$")
- code: `farrier/farrier/_vendor/stablemate_core/clock.py::Clock.now`

### method: monotonic
- sig: `monotonic() -> float`
- abstract: true
- does: returns elapsed-time clock seconds that do not move backwards
- returns: the current monotonic reading
- verify: json_path(path="return value", matches="^[0-9]+(\\.[0-9]+)?$")
- code: `farrier/farrier/_vendor/stablemate_core/clock.py::Clock.monotonic`

### method: sleep
- sig: `sleep(seconds: float) -> None`
- abstract: true
- does: waits for the requested duration
- returns: `None`
- verify: json_path(path="return value", absent=true)
- code: `farrier/farrier/_vendor/stablemate_core/clock.py::Clock.sleep`

### method: SystemClock.now
- sig: `now() -> datetime`
- does: returns the system wall-clock date and time
- verify: json_path(path="return value", matches="^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]+)?$")
- returns: the value produced by the system wall clock
- verify: json_path(path="return value", matches="^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]+)?$")
- code: `farrier/farrier/_vendor/stablemate_core/clock.py::SystemClock.now`

### method: SystemClock.monotonic
- sig: `monotonic() -> float`
- does: returns the system monotonic clock reading
- returns: a non-decreasing elapsed-time reading
- verify: json_path(path="return value", matches="^[0-9]+(\\.[0-9]+)?$")
- code: `farrier/farrier/_vendor/stablemate_core/clock.py::SystemClock.monotonic`

### method: SystemClock.sleep
- sig: `sleep(seconds: float) -> None`
- does: waits for the requested duration using the system clock
- verify: count(subject="operating system sleep calls", equals=1)
- returns: `None`
- verify: json_path(path="return value", absent=true)
- code: `farrier/farrier/_vendor/stablemate_core/clock.py::SystemClock.sleep`

## Fields

### field: SYSTEM_CLOCK
- type: `SystemClock`
- default: the module's single system-clock instance
- required: true
- semantics: provides the default clock for callers that inject a clock contract
- verify: count(subject="default system clock instances", equals=1)
- code: `farrier/farrier/_vendor/stablemate_core/clock.py::SYSTEM_CLOCK`
