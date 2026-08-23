"""Pull the frames around a step out of a run's recording (``ostler qa frames``).

The report says where each step sits in the recording — a step's ``started_offset_ms``
and the recording's ``actionStartOffsetMs`` are on the same clock, and
:mod:`ostler.qa.report` does the subtraction. Seeking a 20 s video to 0:06.4 by hand is
still the slow part of reading one, and a single frame is rarely what a reader wants: the
question is what the screen showed *around* the moment, not at it. This module names a
step (or a raw position), widens it by ``around`` seconds on each side, and writes one PNG
per ``1/fps`` seconds of that window under ``qa/frames/<step>/``, each file named by its
position in the recording, with an ``index.md`` a reader opens to see them in order.

ffmpeg does the decoding. It is the same binary the recorder needed, so a run that has a
recording has it; a machine without one gets a clear error, not a traceback.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ostler.qa.report import ReportError, build_report, video_clock
from ostler.qa.session import QA_DIRNAME, scratch_dirname

FRAMES_DIRNAME = "frames"
INDEX_FILE = "index.md"
DEFAULT_AROUND_SECONDS = 1.0
DEFAULT_FPS = 10.0


class FramesError(RuntimeError):
    """The step, the recording or ffmpeg is not there to extract from."""


@dataclass(frozen=True)
class Frame:
    seconds: float
    path: Path


@dataclass(frozen=True)
class FramesResult:
    """What was written: the window in recording seconds, the frames in order, the index."""

    video: str
    step_id: str
    step_label: str
    scenario: str
    at: float
    until: float
    start: float
    end: float
    out_dir: Path
    index: Path
    frames: list[Frame] = field(default_factory=list)


def find_step(data: Mapping[str, Any], step: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """The ``(scenario, step)`` the name picks out of a report's data.

    An exact step id wins; failing that, a unique case-insensitive substring of a step's
    label — the ids are long and the label is what a reader saw in the report.
    """
    exact = [
        (scenario, view)
        for scenario in data["scenarios"]
        for view in scenario["steps"]
        if view["id"] == step
    ]
    if len(exact) == 1:
        return exact[0]
    needle = step.casefold()
    loose = [
        (scenario, view)
        for scenario in data["scenarios"]
        for view in scenario["steps"]
        if needle and needle in view["label"].casefold()
    ]
    if len(loose) == 1:
        return loose[0]
    if len(loose) > 1:
        names = ", ".join(f"{s['id']}:{v['id']}" for s, v in loose[:6])
        raise FramesError(f"{step!r} matches {len(loose)} steps ({names}…); give the step id")
    raise FramesError(f"no step named {step!r} in this run")


def frame_window(
    data: Mapping[str, Any],
    *,
    step: str | None = None,
    at: float | None = None,
    target: str | None = None,
    around: float = DEFAULT_AROUND_SECONDS,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The recording and the placement ``{"at", "until"}`` (seconds) a request names,
    before widening. ``step`` reads the report's placement; ``at`` is a raw position in
    the recording of ``target`` (or the only recording)."""
    if (step is None) == (at is None):
        raise FramesError("name exactly one of a step or a position (--step / --at)")
    recordings = {r["target"]: r for r in data["recordings"]}
    if not recordings:
        raise FramesError("this run has no recording")
    if step is not None:
        scenario, view = find_step(data, step)
        if view.get("video") is None:
            if scenario["target"] not in recordings:
                raise FramesError(
                    f"step {view['id']!r} ran against `{scenario['target']}`, which was not recorded"
                )
            raise FramesError(
                f"step {view['id']!r} has no place in the recording — the run predates step "
                "timestamps, or the step ran outside the recorded window"
            )
        recording = recordings[scenario["target"]]
        return recording, {
            "at": float(view["video"]["at"]),
            "until": float(view["video"]["until"]),
            "stepId": view["id"],
            "stepLabel": view["label"],
            "scenario": scenario["id"],
        }
    if at is None:  # the first check above proved it; this is for the type-checker
        raise FramesError("name exactly one of a step or a position (--step / --at)")
    if target is None:
        if len(recordings) > 1:
            raise FramesError(
                "several targets were recorded (" + ", ".join(sorted(recordings)) + "); name one with --target"
            )
        target = next(iter(recordings))
    recording = recordings.get(target)
    if recording is None:
        raise FramesError(f"target {target!r} was not recorded")
    position = float(at)
    if position < 0:
        raise FramesError("--at is a position in the recording and cannot be negative")
    return recording, {"at": position, "until": position, "stepId": "", "stepLabel": "", "scenario": ""}


def extract_frames(
    spec_dir: Path,
    *,
    step: str | None = None,
    at: float | None = None,
    target: str | None = None,
    around: float = DEFAULT_AROUND_SECONDS,
    fps: float = DEFAULT_FPS,
    label: str | None = None,
    ffmpeg: str = "ffmpeg",
) -> FramesResult:
    """Write the frames around a step (or position) of a run's recording and index them.

    The window is ``[at - around, until + around]`` clamped to the file; one frame every
    ``1/fps`` seconds of it lands in ``<spec>/qa/frames/<step-id>/`` (``qa/<label>/…`` for
    a dry run) as ``<seconds>s.png`` — the position in the recording, so the file names
    read as the player's clock. The directory is emptied first: a re-run with a different
    window must not leave last time's frames mixed in.
    """
    if around < 0:
        raise FramesError("--around cannot be negative")
    if fps <= 0:
        raise FramesError("--fps must be positive")
    if shutil.which(ffmpeg) is None:
        raise FramesError(f"{ffmpeg} is not installed — it decodes the recording")
    spec_dir = Path(spec_dir)
    try:
        data = build_report(spec_dir, label=label)
    except ReportError as exc:
        raise FramesError(str(exc)) from exc
    recording, place = frame_window(data, step=step, at=at, target=target, around=around)
    video = spec_dir / recording["path"]
    if not video.is_file():
        raise FramesError(f"recording {recording['path']} is not on this machine")
    duration = recording.get("durationSeconds")
    start = max(0.0, place["at"] - around)
    end = place["until"] + around
    if duration is not None:
        end = min(end, float(duration))
    if end < start:
        end = start
    qa_dirname = QA_DIRNAME if label is None else scratch_dirname(label)
    slug = place["stepId"] or f"at-{place['at']:.3f}s"
    out_dir = spec_dir / qa_dirname / FRAMES_DIRNAME / slug
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    # One frame at `start`, then one every 1/fps until `end` inclusive: `-t` bounds the
    # decode to the window, `fps=` resamples it, and `-ss` before `-i` seeks cheaply.
    span = max(end - start, 1.0 / fps)
    pattern = out_dir / "frame-%05d.png"
    argv = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{start:.3f}", "-i", str(video), "-t", f"{span:.3f}",
        "-vf", f"fps={fps:g}", "-start_number", "0", str(pattern),
    ]
    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FramesError(f"ffmpeg failed ({proc.returncode}): {proc.stderr.strip()}")
    frames: list[Frame] = []
    for index, raw in enumerate(sorted(out_dir.glob("frame-*.png"))):
        seconds = round(start + index / fps, 3)
        named = out_dir / f"{seconds:08.3f}s.png"
        raw.rename(named)
        frames.append(Frame(seconds=seconds, path=named))
    if not frames:
        raise FramesError(f"ffmpeg wrote no frame for {video_clock(start)}–{video_clock(end)} of {recording['path']}")
    result = FramesResult(
        video=str(recording["path"]),
        step_id=place["stepId"],
        step_label=place["stepLabel"],
        scenario=place["scenario"],
        at=place["at"],
        until=place["until"],
        start=start,
        end=end,
        out_dir=out_dir,
        index=out_dir / INDEX_FILE,
        frames=frames,
    )
    result.index.write_text(render_index(result, spec_dir=spec_dir), encoding="utf-8")
    return result


def _covered(result: FramesResult) -> str:
    """First to last frame written — the window as sampled, which stops short of ``end``
    by up to one frame interval."""
    return f"{video_clock(result.frames[0].seconds)}–{video_clock(result.frames[-1].seconds)}"


def render_index(result: FramesResult, *, spec_dir: Path) -> str:
    """``index.md`` beside the frames: what they are of, then each frame in order, the
    ones inside the step's own span marked so the lead-in and lead-out read as such."""
    lines = []
    if result.step_id:
        lines.append(f"# Frames around step `{result.step_id}`")
        lines.append("")
        lines.append(f"**{result.step_label or result.step_id}** (scenario `{result.scenario}`)  ")
        span = video_clock(result.at) + (f"–{video_clock(result.until)}" if result.until > result.at else "")
        lines.append(f"The step ran at {span} of `{result.video}`; frames cover {_covered(result)}.")
    else:
        lines.append(f"# Frames around {video_clock(result.at)} of `{result.video}`")
        lines.append("")
        lines.append(f"Frames cover {_covered(result)}.")
    lines.append("")
    for frame in result.frames:
        inside = result.at <= frame.seconds <= result.until if result.step_id else frame.seconds == result.at
        marker = " ← during the step" if inside and result.step_id else ""
        lines.append(f"## {video_clock(frame.seconds)} ({frame.seconds:.3f}s){marker}")
        lines.append("")
        lines.append(f"![{frame.seconds:.3f}s]({frame.path.name})")
        lines.append("")
    return "\n".join(lines)
