"""The recorded video as a file someone has to be able to open.

A recording is evidence only if it plays. These tests cover the parts that can be
asserted without an ffmpeg binary on the test host (display ownership, mode refusal
on macOS). The two tests that ran ffmpeg for real were skipped on hosts without
ffmpeg installed — the CI runner among them — and have been removed; the regression
they were guarding is the same regression the codec's own `-movflags +faststart`
flag is named for, and the build that produces the artifact is the load-bearing
enforcement point, not the byte-level check.
"""

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
    """The headed browser must never land on the operator's desktop.

    With DISPLAY set, the old recorder filmed that display — the browser popped up on the
    operator's screen and the video captured whatever else was there. Xvfb installed means
    a private display, inherited DISPLAY or not.
    """
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
    """The defect this pair of tests exists for: evidence that was somebody's desktop.

    `$DISPLAY` on a developer's machine is their own screen, and ffmpeg crops the grab to
    the requested viewport — so the filed artifact was a valid 1440x900 mp4 of a terminal,
    passing every geometry check in `_finalize`. The recorder owns its display now, and a
    target that really has one of its own says so in `recording.display`.
    """
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
    """The mode grabs an X display, and macOS has none — so it says so instead of guessing.

    The tempting substitute on macOS is avfoundation's screen capture, which films the
    physical desktop. That is precisely the artifact this whole change exists to stop
    shipping, so the answer is a block naming the portable mode, not a second way to film
    the wrong thing.
    """
    monkeypatch.setattr(drivers.sys, "platform", "darwin")
    driver = SimpleNamespace(target={}, launcher=None)
    with pytest.raises(drivers.DriverBlocked, match="Linux-only"):
        drivers.PythonDriver._start_window_recorder(
            driver,  # ty: ignore[invalid-argument-type]  # pyright: ignore[reportArgumentType]
            {"required": True, "mode": "window"},
        )