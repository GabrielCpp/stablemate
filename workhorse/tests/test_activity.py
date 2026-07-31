"""Tests for "what is the run working on right now".

A workflow says it with a flagged log record (``logger.info(msg, extra={"activity":
True})``), because a state is one method that may do several things and the interesting
one is whichever it is doing now. Three seams:

- ``pyflow.activity.ActivityLog`` publishes the last flagged message as the
  ``activity`` label, unprefixed, and keeps it across a transition's ``rebase``;
- unlike most labels, activity and work_id also ride the LIVE liveness metrics
  (``workhorse.node.active`` and the run heartbeat), so a monitor can show what the run
  is doing while the node span is still open — and only those two keys do, to keep
  metric attribute cardinality bounded;
- they ride prefixed and unprefixed alike: the ``wf.``-prefixed spelling outlived the
  YAML front-end that minted it, because the spans already in a collector's store use
  it and are still queried alongside the new ones.

Run: uv run python workhorse/tests/test_activity.py   (or via pytest)
"""
from __future__ import annotations

import contextlib
import importlib
import logging

from workhorse import otel
from workhorse.pyflow import activity as pyflow_activity

test_otel = importlib.import_module("tests.test_otel")


@contextlib.contextmanager
def _live():
    """Make ``otel.set_labels`` really land somewhere readable.

    ``_telemetry()`` builds a facade over fakes but does not install it, and the module
    functions are no-ops with nothing active — so a tracker test that skipped this
    would pass while publishing into the void."""
    t, _tracer, meter, _sd = test_otel._telemetry()
    saved = otel._active
    otel._active = t
    try:
        yield t, meter
    finally:
        otel._active = saved


def _logger(name: str) -> logging.Logger:
    """A logger whose INFO records actually reach the filters. A logger left at its
    inherited WARNING level drops the flagged line before any filter sees it, which
    would make every assertion below vacuously true."""
    log = logging.getLogger(f"tests.activity.{name}")
    log.setLevel(logging.INFO)
    log.filters.clear()
    return log


# --------------------------------------------------------------------------- #
# The live path — wf.activity/wf.work_id ride node.active + the run heartbeat
# --------------------------------------------------------------------------- #
def test_activity_rides_the_node_active_gauge():
    t, _tracer, meter, _sd = test_otel._telemetry()
    t.set_labels({"wf.activity": "reviewing X", "wf.work_id": "ACME-1",
                  "wf.phase": "qa"})
    t.record_event({"node": "impl", "seq": 1, "phase": "enter"})

    gauge = meter.instruments["workhorse.node.active"]
    _kind, value, attrs = gauge.records[-1]
    assert value == 1, gauge.records
    assert attrs["node"] == "impl", attrs
    assert attrs["wf.activity"] == "reviewing X", attrs
    assert attrs["wf.work_id"] == "ACME-1", attrs
    # Only the two dashboard keys ride the gauge; other labels stay off it so
    # metric attribute cardinality stays bounded.
    assert "wf.phase" not in attrs, attrs


def test_activity_rides_the_run_heartbeat():
    t, _tracer, meter, _sd = test_otel._telemetry()
    t.set_labels({"wf.activity": "seeding", "wf.work_id": "ACME-2"})
    t.record_event({"node": "seed", "seq": 1, "phase": "enter"})
    t._beat_once()

    beats = meter.instruments["workhorse.run.heartbeat"]
    _kind, _value, attrs = beats.records[-1]
    assert attrs["node"] == "seed", attrs
    assert attrs["wf.activity"] == "seeding", attrs
    assert attrs["wf.work_id"] == "ACME-2", attrs


def test_live_attrs_omit_absent_labels():
    t, _tracer, meter, _sd = test_otel._telemetry()
    # No labels set at all — the gauge carries just the node, never a blank attr.
    t.record_event({"node": "plan", "seq": 1, "phase": "enter"})
    gauge = meter.instruments["workhorse.node.active"]
    _kind, _value, attrs = gauge.records[-1]
    assert attrs == {"node": "plan"}, attrs


def test_unprefixed_labels_ride_the_gauge_too():
    # pyflow does not prefix its labels, so the promotion has to recognize both
    # spellings or a Python workflow could never reach the live gauges at all.
    t, _tracer, meter, _sd = test_otel._telemetry()
    t.set_labels({"activity": "assessing legacy/report/list", "work_id": "ACME-3",
                  "phase": "survey"})
    t.record_event({"node": "assess", "seq": 1, "phase": "enter"})
    gauge = meter.instruments["workhorse.node.active"]
    _kind, value, attrs = gauge.records[-1]
    assert value == 1, gauge.records
    assert attrs == {"node": "assess", "activity": "assessing legacy/report/list",
                     "work_id": "ACME-3"}, attrs


# --------------------------------------------------------------------------- #
# pyflow — the flagged log record IS the activity
# --------------------------------------------------------------------------- #
def test_a_flagged_log_record_becomes_the_activity_label():
    with _live() as (t, _meter):
        log = _logger("flag")
        pyflow_activity.install(log).rebase({"work_id": "ACME-1"})

        log.info("assessing %s", "legacy/report/list", extra={"activity": True})
        assert t._labels == {
            "work_id": "ACME-1",
            "activity": "assessing legacy/report/list",
        }, t._labels

        # An ordinary line is just a log line. Every node logs; only the ones that
        # opt in are claiming to describe the run.
        log.info("wrote 12 bullets")
        assert t._labels["activity"] == "assessing legacy/report/list", t._labels


def test_the_activity_survives_a_transitions_rebase():
    # Sticky is the whole point: a state that flags once and then works for an hour
    # must stay correctly labelled, and every transition rebases the labels.
    with _live() as (t, _meter):
        log = _logger("sticky")
        tracker = pyflow_activity.install(log)

        log.info("freezing the unit list", extra={"activity": True})
        tracker.rebase({"work_id": "ACME-2"})
        assert t._labels == {
            "work_id": "ACME-2",
            "activity": "freezing the unit list",
        }, t._labels


def test_a_rebase_replaces_the_declared_labels():
    # Same contract as `otel.set_labels`: a key that stopped resolving must stop
    # appearing rather than linger at its last value.
    with _live() as (t, _meter):
        tracker = pyflow_activity.install(_logger("rebase"))
        tracker.rebase({"work_id": "ACME-A", "phase": "survey"})
        tracker.rebase({"work_id": "ACME-B"})
        assert t._labels == {"work_id": "ACME-B"}, t._labels


def test_a_bad_format_string_costs_the_activity_and_nothing_else():
    with _live() as (t, _meter):
        log = _logger("badfmt")
        pyflow_activity.install(log)
        log.info("assessing %s", "one", extra={"activity": True})

        # Two placeholders, one argument: `getMessage()` raises. Instrumentation must
        # never be the thing that ends an unattended run, so the old activity stands.
        log.info("comparing %s to %s", "one", extra={"activity": True})
        assert t._labels == {"activity": "assessing one"}, t._labels


def test_installing_twice_returns_the_one_tracker():
    # `handoff` drives a sub-workflow through a recursive `drive()` on the same
    # logger; a second tracker would publish over the first and lose the sub-flow's
    # activity on the parent's next transition.
    log = _logger("install")
    first = pyflow_activity.install(log)
    assert pyflow_activity.install(log) is first
    trackers = [f for f in log.filters if isinstance(f, pyflow_activity.ActivityLog)]
    assert len(trackers) == 1, log.filters


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
