---
type: concept
slug: thread-pool-isolation
title: Thread pool isolation
---
# Thread pool isolation

Blocking work in the asyncio event loop is queued to a shared default executor, which on an eight-core machine has only 12 worker threads. When one kind of blocking operation saturates the pool, other unrelated work queues indefinitely, causing visible stalls. Groom uses dedicated thread pools for different concerns so one cannot starve another.

## The problem

Before isolation, every blocking call — telemetry ingest (span/metric/log writes), dashboard store reads, file system operations, Docker subprocess execution, and desktop notifications — competed for the same 12 threads. A slow disk or a series of Docker commands could fill every slot, causing telemetry writes to queue (which then blocks the store reads that populate the dashboard, making the UI unresponsive) even though GETs still answer in milliseconds.

## The solution

Each concern gets its own `Pool` instance with a bounded worker count. The INGEST pool handles telemetry writes; the QUERY pool handles dashboard store reads; slow unbounded work stays on the default executor.

## Isolation boundaries

- **INGEST**: OTLP span, metric, and log writes. Small pool (4 workers default) because writes serialize on the store's single connection anyway.
- **QUERY**: Store reads serving the dashboard live tick and the browser. Small pool (4 workers default) for the same reason.
- **Default executor**: Docker subprocesses, file system reads/writes, workspace volume operations, desktop notifications. Stays unbounded because these operations may block for minutes and should not wedge the isolated pools.

## Implementation: Pool class

The `Pool` class provides lazy instantiation, sizing from the environment, and a `run()` method equivalent to `asyncio.to_thread()` but on the isolated executor. Worker count is read at first use, not import time, so tests can set environment variables and get the pool size they ask for.

## Shutdown semantics

`shutdown(wait=False, cancel_futures=True)` is called on both pools at process shutdown. The non-blocking shutdown is intentional: blocking on a store call that itself is waiting on a disk saturation event would hang the shutdown and is precisely the problem isolation was meant to prevent.

- code: `groom/groom/pools.py::Pool`
- code: `groom/groom/pools.py::shutdown_all`
- code: `groom/groom/pools.py::INGEST`
- code: `groom/groom/pools.py::QUERY`
- tests: `groom/tests/test_pools.py`
