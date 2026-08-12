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

from ostler.qa.drivers import DisplayRecorder


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
    return DisplayRecorder(session, "web", width=320, height=240, fps=5)  # ty: ignore[invalid-argument-type]


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
