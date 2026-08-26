"""The recorded video as a file someone has to be able to open.

A recording is evidence only if it plays. These run ffmpeg for real — the argv is not the
claim, the bytes it writes are — and skip where ffmpeg is not installed.
"""

from __future__ import annotations

import os
import shutil
import struct
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from ostler.qa import drivers
from ostler.qa.drivers import DisplayRecorder, _is_static


def _atoms(path: Path) -> list[str]:
    """The top-level atom types, in the order a player reads them."""
    order: list[str] = []
    size = path.stat().st_size
    offset = 0
    with path.open("rb") as handle:
        while offset < size:
            handle.seek(offset)
            header = handle.read(8)
            if len(header) < 8:
                break
            length = struct.unpack(">I", header[:4])[0]
            order.append(header[4:8].decode("latin1"))
            if length == 0:
                break
            offset += length
    return order


def _recorder(tmp_path: Path) -> DisplayRecorder:
    session = SimpleNamespace(qa_dir=tmp_path, offset_ms=lambda: 0, append=lambda record: None)
    return DisplayRecorder(
        session,  # ty: ignore[invalid-argument-type]  # pyright: ignore[reportArgumentType]
        "web",
        width=320,
        height=240,
        fps=5,
    )


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
def test_a_recording_is_playable_before_it_is_fully_downloaded(tmp_path: Path) -> None:
    """`moov` is the atom a player needs first, and mp4 writes it last by default.

    A reviewer opening the evidence in a browser gets a file that does not play at all,
    which is indistinguishable from a scenario whose recording never started — so the run
    reads as unevidenced when the video is sitting right there, complete.

    Filmed from a synthetic source rather than X11: the atom order is a muxer property, and
    tying the check to a live display would mean not running it anywhere it matters.
    """
    recorder = _recorder(tmp_path)
    argv = recorder.argv()
    assert argv[-3:-1] == ["-movflags", "+faststart"], argv

    path = Path(argv[-1])
    path.parent.mkdir(parents=True, exist_ok=True)
    source = ["-f", "lavfi", "-i", "testsrc=size=320x240:rate=5", "-t", "1"]
    # Everything after the input is the muxing half under test, verbatim.
    encode = argv[argv.index("-c:v") :]
    subprocess.run(  # noqa: S603 — fixed argv, ffmpeg resolved by the skipif above
        ["ffmpeg", "-y", "-loglevel", "error", *source, *encode],  # noqa: S607
        check=True,
        env={**os.environ, "AV_LOG_FORCE_NOCOLOR": "1"},
    )

    order = _atoms(path)
    assert "moov" in order and "mdat" in order, order
    assert order.index("moov") < order.index("mdat"), (
        f"the video will not stream: {order}"
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


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
def test_a_recording_of_a_display_nothing_was_drawn_on_is_not_evidence(tmp_path: Path) -> None:
    """The failure that survives owning the display: Xvfb comes up and the browser never paints.

    Filmed for real, both ways, because the claim is about the bytes: an unchanging capture
    is refused, and anything with motion in it is not. The moving case is the one that
    matters — a guard that fires on a real session would block runs that worked.
    """
    static = tmp_path / "static.mp4"
    moving = tmp_path / "moving.mp4"
    for path, source in ((static, "color=c=gray:s=320x240:r=5:d=4"), (moving, "testsrc=s=320x240:r=5:d=4")):
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", source,
             "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
            check=True,
            timeout=120,
        )

    assert _is_static(static, 4.0)
    assert not _is_static(moving, 4.0)


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
