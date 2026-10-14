"""A watched run's database snapshot, advanced by committed OTLP batches."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from groom.models import LIVENESS_METRICS


@dataclass
class LiveHistory:
    """Only open panes retain history; span identities make retries idempotent."""

    log_limit: int
    transcript_limit: int = 200
    loaded: bool = False
    spans: dict[str, dict[str, Any]] = field(default_factory=dict)
    logs: list[dict[str, Any]] = field(default_factory=list)
    metrics: list[dict[str, Any]] = field(default_factory=list)
    transcript: list[dict[str, Any]] = field(default_factory=list)
    offsets: dict[str, int] = field(default_factory=dict)
    partial: dict[str, bytes] = field(default_factory=dict)
    calls: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_ts: dict[str, float] = field(default_factory=dict)

    def update_spans(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            self.spans[row["span_id"]] = {
                "start_ts": row["start_ts"],
                "end_ts": row["end_ts"],
                "status": row["status"],
                "node": row.get("node", ""),
                "name": row.get("name", ""),
                "slug": row.get("slug")
                or (row.get("attrs") or {}).get("workhorse.visit.slug", ""),
            }

    def update_logs(self, rows: list[dict[str, Any]]) -> None:
        self.logs = sorted(
            [*reversed(rows), *self.logs], key=lambda row: row["ts"], reverse=True
        )[:self.log_limit]

    def update_metrics(self, rows: list[dict[str, Any]]) -> None:
        retained = [row for row in rows if row["name"] not in LIVENESS_METRICS]
        self.metrics = sorted(
            [*reversed(retained), *self.metrics], key=lambda row: row["ts"], reverse=True
        )[:self.log_limit]

    def feed_transcript(self, slug: str, data: bytes) -> None:
        """Take the next bytes of one turn's transcript, keyed by its slug so a file renamed after capture continues where its live twin stopped."""
        held = self.partial.pop(slug, b"")
        start = self.offsets.get(slug, 0) - len(held)
        self.offsets[slug] = self.offsets.get(slug, 0) + len(data)
        *lines, tail = (held + data).split(b"\n")
        if tail:
            self.partial[slug] = tail
        for line in lines:
            self._take_transcript_line(slug, line, f"{slug}:{start}")
            start += len(line) + 1
        self.transcript = sorted(self.transcript, key=lambda row: row["ts"])[-self.transcript_limit:]
        kept = {id(row) for row in self.transcript}
        self.calls = {key: row for key, row in self.calls.items() if id(row) in kept}

    def _take_transcript_line(self, slug: str, line: bytes, key: str) -> None:
        try:
            record = json.loads(line)
        except ValueError:
            return
        if not isinstance(record, dict):
            return
        if record.get("truncated"):
            update: dict[str, Any] = {
                "sessionUpdate": "truncated", "bytes": record.get("bytes", 0)
            }
            meta: dict[str, Any] = {}
        else:
            raw_update, raw_meta = record.get("update"), record.get("_meta") or {}
            if not isinstance(raw_update, dict) or not isinstance(raw_meta, dict):
                return
            update, meta = raw_update, raw_meta
        ts = float(meta.get("ts") or self.last_ts.get(slug, 0.0))
        self.last_ts[slug] = ts
        call_id = str(update.get("toolCallId") or "")
        known = self.calls.get(call_id) if call_id else None
        if known is not None:
            merged = known["update"]
            if update.get("sessionUpdate") == "tool_call":
                merged.update(update)
            else:
                merged.update({k: v for k, v in update.items() if k != "sessionUpdate"})
            return
        row = {
            "key": key,
            "slug": slug,
            "ts": ts,
            "node": str(meta.get("node") or ""),
            "parent": str(meta.get("parent") or ""),
            "update": dict(update),
        }
        self.transcript.append(row)
        if call_id:
            self.calls[call_id] = row

    def recent(self) -> list[dict[str, Any]]:
        """Time-ordered evidence from every persisted telemetry family."""
        spans = sorted(self.spans.values(), key=lambda row: row["end_ts"], reverse=True)
        rows = [
            *({**row, "kind": "log"} for row in self.logs),
            *({**row, "kind": "metric"} for row in self.metrics),
            *({**row, "kind": "transcript"} for row in reversed(self.transcript)),
            *({**row, "kind": "span", "ts": row["end_ts"]} for row in spans[:self.log_limit]),
        ]
        return sorted(rows, key=lambda row: row["ts"], reverse=True)

    def facts(self) -> dict[str, Any]:
        if not self.spans:
            return {}
        return {
            "span_count": len(self.spans),
            "error_count": sum(row["status"] == "ERROR" for row in self.spans.values()),
            "first_ts": min(row["start_ts"] for row in self.spans.values()),
            "last_ts": max(row["end_ts"] for row in self.spans.values()),
        }
