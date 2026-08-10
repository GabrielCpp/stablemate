"""What a run keeps of the agent's own words.

`prompt.md` says what a node was told and `output.json` what it answered; the reasoning
and the tool calls in between live only in the CLI's session store — on one host, keyed by
nothing telemetry can join on, and pruned whenever the CLI likes. So each turn is captured
into the run dir under the same visit key the rest of the turn record uses, from the store
where there is one and from a tee of the redacted stream where there is not.

    ./.venv/bin/python tests/test_transcript.py
    ./.venv/bin/python -m pytest tests/test_transcript.py
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from workhorse import turnkey
from workhorse.runner import transcript


def _begin(run_dir: Path, node: str = "qa-plan") -> str:
    """Open a visit the way the engine does, and return its key slug."""
    turnkey.begin(run_dir, node)
    key = turnkey.current()
    assert key is not None
    return key.slug


def _store(tmp: Path, session_id: str, text: str = '{"type":"assistant"}\n') -> None:
    """Install a fake backend store holding one session, and point capture at it."""
    path = tmp / "store" / f"{session_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    transcript._STORES["acme-cli"] = lambda sid: (
        [tmp / "store" / f"{sid}.jsonl"] if (tmp / "store" / f"{sid}.jsonl").is_file() else []
    )


def _meta(stem: Path) -> dict:
    return json.loads(Path(f"{stem}.meta.json").read_text())


def _reset() -> None:
    turnkey.clear()
    transcript.unbind()
    transcript._STORES.pop("acme-cli", None)


def test_the_store_is_preferred_and_the_tee_it_beats_is_dropped():
    _reset()
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "run"
        run_dir.mkdir()
        transcript.bind(run_dir)
        slug = _begin(run_dir)
        _store(Path(tmp), "sess-1", '{"from":"store"}\n')

        tee = transcript.tee_begin("qa-plan")
        assert tee is not None
        tee.write('{"from":"tee"}\n')
        tee.close()

        stem = transcript.capture("acme-cli", "qa-plan", "sess-1", tee)

        assert stem is not None
        assert Path(f"{stem}.jsonl").read_text() == '{"from":"store"}\n'
        assert _meta(stem)["source"] == "store"
        # The poorer copy of something already kept is not evidence, it is bytes.
        assert not tee.path.exists()
        assert stem.name == f"{slug}__sess-1"


def test_a_backend_with_no_store_is_captured_from_the_tee():
    _reset()
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "run"
        run_dir.mkdir()
        transcript.bind(run_dir)
        _begin(run_dir)

        tee = transcript.tee_begin("qa-plan")
        assert tee is not None
        tee.write('{"from":"tee"}\n')
        tee.close()

        stem = transcript.capture("no-such-cli", "qa-plan", "sess-2", tee)

        assert stem is not None
        assert Path(f"{stem}.tee.jsonl").read_text() == '{"from":"tee"}\n'
        meta = _meta(stem)
        assert meta["source"] == "tee"
        assert meta["session_id"] == "sess-2"
        assert meta["node"] == "qa-plan"


def test_the_tee_stops_at_the_cap_and_says_so():
    _reset()
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "run"
        run_dir.mkdir()
        transcript.bind(run_dir, max_bytes=32)
        _begin(run_dir)

        tee = transcript.tee_begin("qa-plan")
        assert tee is not None
        for _ in range(20):
            tee.write("x" * 16 + "\n")
        tee.close()

        assert tee.truncated
        stem = transcript.capture("no-such-cli", "qa-plan", "sess-3", tee)
        assert stem is not None
        # A transcript that announces where it stopped is usable evidence; one that just
        # ends is indistinguishable from a turn that died.
        last = Path(f"{stem}.tee.jsonl").read_text().strip().splitlines()[-1]
        assert json.loads(last)["truncated"] is True
        assert _meta(stem)["truncated"] is True


def test_the_store_capture_is_also_capped():
    _reset()
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "run"
        run_dir.mkdir()
        transcript.bind(run_dir, max_bytes=64)
        _begin(run_dir)
        _store(Path(tmp), "sess-4", "y" * 4096)

        stem = transcript.capture("acme-cli", "qa-plan", "sess-4")

        assert stem is not None
        assert _meta(stem)["truncated"] is True
        assert Path(f"{stem}.jsonl").stat().st_size < 4096


def test_capture_is_off_when_the_run_asked_for_it_to_be():
    _reset()
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "run"
        run_dir.mkdir()
        transcript.bind(run_dir, enabled=False)
        _begin(run_dir)
        _store(Path(tmp), "sess-5")

        assert transcript.tee_begin("qa-plan") is None
        assert transcript.capture("acme-cli", "qa-plan", "sess-5") is None
        assert not (run_dir / transcript.TRANSCRIPTS_DIR).exists()


def test_a_turn_outside_a_visit_is_not_filed_under_somebody_elses():
    _reset()
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "run"
        run_dir.mkdir()
        transcript.bind(run_dir)
        _begin(run_dir, "qa-plan")
        _store(Path(tmp), "sess-6")

        # A library caller driving the runner directly, or a `self.call` node: the engine
        # opened no visit for it, and an invented key would collide with a real one.
        assert transcript.tee_begin("implement") is None
        assert transcript.capture("acme-cli", "implement", "sess-6") is None


def test_each_lap_of_a_looping_node_is_captured_separately():
    _reset()
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "run"
        run_dir.mkdir()
        transcript.bind(run_dir)

        for lap in range(1, 4):
            _begin(run_dir)
            _store(Path(tmp), f"sess-lap{lap}", f'{{"lap":{lap}}}\n')
            transcript.capture("acme-cli", "qa-plan", f"sess-lap{lap}")

        kept = sorted(
            p.name for p in (run_dir / transcript.TRANSCRIPTS_DIR).glob("*.jsonl")
        )
        assert len(kept) == 3
        assert len(set(kept)) == 3


def test_capture_never_faults_the_turn():
    _reset()
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "run"
        run_dir.mkdir()
        transcript.bind(run_dir)
        _begin(run_dir)
        # A store resolver that blows up, and a transcripts dir that cannot be created
        # because a file already holds its name.
        transcript._STORES["acme-cli"] = _raise
        (run_dir / transcript.TRANSCRIPTS_DIR).write_text("not a directory")

        assert transcript.capture("acme-cli", "qa-plan", "sess-7") is None
        assert transcript.tee_begin("qa-plan") is None


def _raise(_session_id: str) -> list[Path]:
    raise OSError("store unreadable")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
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
