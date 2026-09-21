"""The recorded video as a file someone has to be able to open."""

from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from ostler.qa import drivers
from ostler.qa.drivers import DisplayRecorder


def _recorder(tmp_path: Path) -> DisplayRecorder:
    session = SimpleNamespace(qa_dir=tmp_path, offset_ms=lambda: 0, append=lambda record: None)
    return DisplayRecorder(
        session,  # ty: ignore[invalid-argument-type]  # pyright: ignore[reportArgumentType]
        "web",
        width=320,
        height=240,
        fps=5,
    )


def test_recording_uses_a_private_display_even_when_one_is_inherited(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The headed browser must never land on the operator's desktop."""
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("ostler.qa.drivers.time.sleep", lambda seconds: None)
    spawned: list[list[str]] = []

    class _Proc:
        def __init__(self, argv: list[str], **kwargs: object) -> None:
            spawned.append(argv)
            self.stdin = None

        def poll(self) -> None:
            return None

    monkeypatch.setattr("ostler.qa.drivers.subprocess.Popen", _Proc)
    recorder = _recorder(tmp_path)
    env = recorder.start()
    assert spawned[0][0] == "Xvfb"
    assert env["DISPLAY"] == spawned[0][1] != ":0"
    assert recorder.argv()[recorder.argv().index("-i") + 1] == f"{env['DISPLAY']}.0"


def test_the_recorder_never_films_whatever_screen_display_happens_to_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The defect this pair of tests exists for: evidence that was somebody's desktop."""
    monkeypatch.setenv("DISPLAY", ":0")
    assert _recorder(tmp_path).display == ""

    session = SimpleNamespace(qa_dir=tmp_path, offset_ms=lambda: 0, append=lambda record: None)
    declared = DisplayRecorder(
        session,  # ty: ignore[invalid-argument-type]  # pyright: ignore[reportArgumentType]
        "web",
        width=320,
        height=240,
        fps=5,
        display=":99",
    )
    assert declared.display == ":99"
    assert ":99.0" in declared.argv()


def test_window_mode_is_refused_where_it_cannot_work_rather_than_filmed_wrong(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The mode grabs an X display, and macOS has none — so it says so instead of guessing."""
    monkeypatch.setattr(drivers.sys, "platform", "darwin")
    driver = SimpleNamespace(target={}, launcher=None)
    with pytest.raises(drivers.DriverBlocked, match="Linux-only"):
        drivers.PythonDriver._start_window_recorder(
            driver,  # ty: ignore[invalid-argument-type]  # pyright: ignore[reportArgumentType]
            {"required": True, "mode": "window"},
        )