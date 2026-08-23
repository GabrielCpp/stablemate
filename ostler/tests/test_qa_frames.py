"""`ostler qa frames`: the frames around a step, pulled out of the run's recording.

ffmpeg is faked — the tests pin what the command asks of it (the seek, the window, the
sampling) and what it makes of the result (file names that are positions in the
recording, an index in order), not the decoder.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from ostler.qa import frames as frames_mod
from ostler.qa.frames import FramesError, extract_frames, find_step
from ostler.qa.report import build_report
from ostler.qa.run import cmd_frames

STEP_ONE = ("s-step-1", "sign in with the provisioned account")
STEP_TWO = ("s-step-2", "land on the tree")


def _log() -> list[dict[str, Any]]:
    return [
        {"kind": "session_start", "run_id": "qa-run-1", "story": "story-1", "ts": "2026-08-22T10:00:00Z"},
        {"kind": "scenario_start", "scenario": "s", "target": "web", "driver": "playwright", "mechanism": "live", "covers": ["ac:1"]},
        {"kind": "step", "id": STEP_ONE[0], "label": STEP_ONE[1], "cmd": "", "exit_code": 0, "driver": "python", "scenario": "s", "started_offset_ms": 10_400, "ended_offset_ms": 12_900},
        {"kind": "step", "id": STEP_TWO[0], "label": STEP_TWO[1], "cmd": "", "exit_code": 0, "driver": "python", "scenario": "s", "started_offset_ms": 12_900, "ended_offset_ms": 13_250},
        {"kind": "scenario_stop", "scenario": "s", "status": "passed", "assertions": 1, "failures": 0},
        {"kind": "video", "path": "qa/videos/web.mp4", "target": "web", "mode": "window", "actionStartOffsetMs": 8000, "actionEndOffsetMs": 28_000, "durationSeconds": 20.0, "width": 1440, "height": 900, "fps": 30.0},
        {"kind": "session_stop", "run_id": "qa-run-1", "status": "passed", "ts": "2026-08-22T10:01:00Z"},
    ]


def _spec(tmp_path: Path, log: list[dict[str, Any]] | None = None, *, video: bool = True) -> Path:
    spec = tmp_path / "docs/specs/story-1"
    (spec / "qa/videos").mkdir(parents=True)
    (spec / "qa/qa-run.ndjson").write_text("".join(json.dumps(r) + "\n" for r in (log or _log())), encoding="utf-8")
    (spec / "qa/run-manifest.json").write_text(json.dumps({"runId": "qa-run-1", "artifacts": []}), encoding="utf-8")
    if video:
        (spec / "qa/videos/web.mp4").write_bytes(b"not really a video")
    return spec


class _FakeFfmpeg:
    """Stands in for ffmpeg: records the argv and writes the frames the window implies."""

    def __init__(self) -> None:
        self.argv: list[str] = []

    def __call__(self, argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        self.argv = argv
        span = float(argv[argv.index("-t") + 1])
        fps = float(argv[argv.index("-vf") + 1].removeprefix("fps="))
        pattern = Path(argv[-1])
        count = int(round(span * fps)) + 1
        for index in range(count):
            (pattern.parent / (pattern.name % index)).write_bytes(b"\x89PNG")
        return subprocess.CompletedProcess(argv, 0, "", "")


@pytest.fixture
def ffmpeg(monkeypatch: pytest.MonkeyPatch) -> _FakeFfmpeg:
    fake = _FakeFfmpeg()
    monkeypatch.setattr(frames_mod.subprocess, "run", fake)
    monkeypatch.setattr(frames_mod.shutil, "which", lambda name: f"/usr/bin/{name}")
    return fake


def test_the_frames_around_a_step_are_named_by_their_place_in_the_recording(tmp_path: Path, ffmpeg: _FakeFfmpeg) -> None:
    spec = _spec(tmp_path)
    result = extract_frames(spec, step=STEP_ONE[0], around=0.5, fps=2)
    # The step sits at 2.4–4.9 s of the recording; half a second either side is 1.9–5.4.
    assert (result.at, result.until, result.start, result.end) == (2.4, 4.9, 1.9, 5.4)
    assert ffmpeg.argv[ffmpeg.argv.index("-ss") + 1] == "1.900"
    assert ffmpeg.argv.index("-ss") < ffmpeg.argv.index("-i")  # seek before decode
    assert ffmpeg.argv[ffmpeg.argv.index("-i") + 1] == str(spec / "qa/videos/web.mp4")
    assert ffmpeg.argv[ffmpeg.argv.index("-t") + 1] == "3.500"
    assert result.out_dir == spec / "qa/frames" / STEP_ONE[0]
    assert [f.path.name for f in result.frames] == [
        "0001.900s.png", "0002.400s.png", "0002.900s.png", "0003.400s.png",
        "0003.900s.png", "0004.400s.png", "0004.900s.png", "0005.400s.png",
    ]
    assert [f.seconds for f in result.frames][:3] == [1.9, 2.4, 2.9]
    index = result.index.read_text(encoding="utf-8")
    assert index.startswith("# Frames around step `s-step-1`")
    assert "**sign in with the provisioned account** (scenario `s`)" in index
    assert "The step ran at 0:02.4–0:04.9 of `qa/videos/web.mp4`; frames cover 0:01.9–0:05.4." in index
    assert "## 0:01.9 (1.900s)\n\n![1.900s](0001.900s.png)" in index
    assert "## 0:02.4 (2.400s) ← during the step" in index
    assert "## 0:05.4 (5.400s)\n" in index and "## 0:05.4 (5.400s) ←" not in index


def test_a_second_extraction_replaces_the_first(tmp_path: Path, ffmpeg: _FakeFfmpeg) -> None:
    spec = _spec(tmp_path)
    wide = extract_frames(spec, step=STEP_ONE[0], around=1.0, fps=2)
    narrow = extract_frames(spec, step=STEP_ONE[0], around=0.0, fps=2)
    assert narrow.out_dir == wide.out_dir
    assert len(list(narrow.out_dir.glob("*.png"))) == len(narrow.frames) < len(wide.frames)


def test_a_step_can_be_named_by_a_fragment_of_its_label(tmp_path: Path, ffmpeg: _FakeFfmpeg) -> None:
    spec = _spec(tmp_path)
    assert extract_frames(spec, step="LAND ON").step_id == STEP_TWO[0]
    data = build_report(spec)
    with pytest.raises(FramesError, match="matches 2 steps"):
        find_step(data, "e")  # both labels contain it
    with pytest.raises(FramesError, match="no step named"):
        find_step(data, "nothing like this")


def test_the_window_is_clamped_to_the_recording(tmp_path: Path, ffmpeg: _FakeFfmpeg) -> None:
    spec = _spec(tmp_path)
    result = extract_frames(spec, step=STEP_ONE[0], around=30.0, fps=1)
    assert (result.start, result.end) == (0.0, 20.0)


def test_a_position_instead_of_a_step(tmp_path: Path, ffmpeg: _FakeFfmpeg) -> None:
    spec = _spec(tmp_path)
    result = extract_frames(spec, at=6.0, around=0.5, fps=2)
    assert result.step_id == ""
    assert result.out_dir == spec / "qa/frames/at-6.000s"
    assert (result.start, result.end) == (5.5, 6.5)
    assert result.index.read_text(encoding="utf-8").startswith("# Frames around 0:06.0 of `qa/videos/web.mp4`")
    with pytest.raises(FramesError, match="exactly one"):
        extract_frames(spec, step=STEP_ONE[0], at=6.0)
    with pytest.raises(FramesError, match="exactly one"):
        extract_frames(spec)


def test_what_cannot_be_extracted_is_said_plainly(tmp_path: Path, ffmpeg: _FakeFfmpeg, monkeypatch: pytest.MonkeyPatch) -> None:
    # A step the ledger never stamped (an older harness) has no place in the recording.
    log = _log()
    del log[2]["started_offset_ms"], log[2]["ended_offset_ms"]
    with pytest.raises(FramesError, match="has no place in the recording"):
        extract_frames(_spec(tmp_path / "a", log), step=STEP_ONE[0])
    # A run with no video record at all.
    with pytest.raises(FramesError, match="no recording"):
        extract_frames(_spec(tmp_path / "b", [r for r in _log() if r["kind"] != "video"]), step=STEP_ONE[0])
    # The record is there but the file is not on this machine (qa/ is not committed).
    with pytest.raises(FramesError, match="not on this machine"):
        extract_frames(_spec(tmp_path / "c", video=False), step=STEP_ONE[0])
    # No decoder.
    monkeypatch.setattr(frames_mod.shutil, "which", lambda name: None)
    with pytest.raises(FramesError, match="ffmpeg is not installed"):
        extract_frames(_spec(tmp_path / "d"), step=STEP_ONE[0])


def test_cmd_frames_prints_the_frames_and_returns_them(tmp_path: Path, ffmpeg: _FakeFfmpeg, capsys: pytest.CaptureFixture[str]) -> None:
    spec = _spec(tmp_path)
    outcome = cmd_frames(spec, step=STEP_TWO[0], around=0.0, fps=10)
    assert outcome.ok, outcome.message
    assert outcome.data["step"] == STEP_TWO[0]
    assert outcome.data["frames"][0]["seconds"] == 4.9
    out = capsys.readouterr().out
    assert out.startswith("5 frame(s) around step s-step-2 (0:04.9–0:05.3 of qa/videos/web.mp4) -> ")
    assert "index: " in out
    failed = cmd_frames(spec, step="no such step")
    assert not failed.ok and failed.message.startswith("qa frames: no step named")
