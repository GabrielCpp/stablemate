"""Tests for "what is the run working on right now"."""
from __future__ import annotations

import contextlib
import importlib
import logging

from workhorse.pyflow import activity as pyflow_activity

test_otel = importlib.import_module("tests.test_otel")


@contextlib.contextmanager
def _live():
    """Make ``otel.set_labels`` really land somewhere readable."""
    t, _tracer, meter, _sd = test_otel._telemetry()
    with test_otel.installed(t):
        yield t, meter


def _logger(name: str) -> logging.Logger:
    """A logger whose INFO records actually reach the filters."""
    log = logging.getLogger(f"tests.activity.{name}")
    log.setLevel(logging.INFO)
    log.propagate = False
    log.filters.clear()
    return log


def test_activity_rides_the_node_active_gauge():
    t, _tracer, meter, _sd = test_otel._telemetry()
    t.set_labels({"wf.activity": "reviewing X", "wf.work_id": "ACME-1",
                  "wf.phase": "qa"})
    t.record_event(test_otel._event("impl", 1, "enter"))

    gauge = meter.instruments["workhorse.node.active"]
    _kind, value, attrs = gauge.records[-1]
    assert value == 1, gauge.records
    assert attrs["node"] == "impl", attrs
    assert attrs["wf.activity"] == "reviewing X", attrs
    assert attrs["wf.work_id"] == "ACME-1", attrs
    assert "wf.phase" not in attrs, attrs


def test_activity_rides_the_run_heartbeat():
    t, _tracer, meter, _sd = test_otel._telemetry()
    t.set_labels({"wf.activity": "seeding", "wf.work_id": "ACME-2"})
    t.record_event(test_otel._event("seed", 1, "enter"))
    t._beat_once()

    beats = meter.instruments["workhorse.run.heartbeat"]
    _kind, _value, attrs = beats.records[-1]
    assert attrs["node"] == "seed", attrs
    assert attrs["wf.activity"] == "seeding", attrs
    assert attrs["wf.work_id"] == "ACME-2", attrs


def test_live_attrs_omit_absent_labels():
    t, _tracer, meter, _sd = test_otel._telemetry()
    t.record_event(test_otel._event("plan", 1, "enter"))
    gauge = meter.instruments["workhorse.node.active"]
    _kind, _value, attrs = gauge.records[-1]
    assert attrs == {"node": "plan"}, attrs


def test_unprefixed_labels_ride_the_gauge_too():
    t, _tracer, meter, _sd = test_otel._telemetry()
    t.set_labels({"activity": "assessing legacy/report/list", "work_id": "ACME-3",
                  "phase": "survey"})
    t.record_event(test_otel._event("assess", 1, "enter"))
    gauge = meter.instruments["workhorse.node.active"]
    _kind, value, attrs = gauge.records[-1]
    assert value == 1, gauge.records
    assert attrs == {"node": "assess", "activity": "assessing legacy/report/list",
                     "work_id": "ACME-3"}, attrs


def test_a_flagged_log_record_becomes_the_activity_label():
    with _live() as (t, _meter):
        log = _logger("flag")
        pyflow_activity.install(log).rebase({"work_id": "ACME-1"})

        log.info("assessing %s", "legacy/report/list", extra={"activity": True})
        assert t._labels == {
            "work_id": "ACME-1",
            "activity": "assessing legacy/report/list",
        }, t._labels

        log.info("wrote 12 bullets")
        assert t._labels["activity"] == "assessing legacy/report/list", t._labels


def test_the_activity_survives_a_transitions_rebase():
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

        log.info("comparing %s to %s", "one", extra={"activity": True})
        assert t._labels == {"activity": "assessing one"}, t._labels


def test_installing_twice_returns_the_one_tracker():
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
