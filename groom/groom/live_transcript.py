"""Tailing a native run's transcript files into its open pane's history."""
from __future__ import annotations

from groom import localfs
from groom.live_history import LiveHistory

TAILED_TURNS = 2


def poll(history: LiveHistory, run_dir: str) -> None:
    """Feed the newest turns' new complete lines to ``history``; a seeding call is a poll from offset zero."""
    files = localfs.transcript_files(run_dir)
    for slug in sorted(files)[-TAILED_TURNS:]:
        data = localfs.read_range(files[slug], history.offsets.get(slug, 0))
        if data:
            history.feed_transcript(slug, data)
