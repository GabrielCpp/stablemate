"""A watched run's database snapshot, advanced by committed OTLP batches."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from groom.models import LIVENESS_METRICS


@dataclass
class LiveHistory:
    """Only open panes retain history; span identities make retries idempotent."""

    log_limit: int
    loaded: bool = False
    spans: dict[str, dict[str, Any]] = field(default_factory=dict)
    logs: list[dict[str, Any]] = field(default_factory=list)
    metrics: list[dict[str, Any]] = field(default_factory=list)

    def update_spans(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            self.spans[row["span_id"]] = {
                "start_ts": row["start_ts"],
                "end_ts": row["end_ts"],
                "status": row["status"],
                "node": row.get("node", ""),
                "name": row.get("name", ""),
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

    def recent(self) -> list[dict[str, Any]]:
        """Time-ordered evidence from every persisted telemetry family."""
        spans = sorted(self.spans.values(), key=lambda row: row["end_ts"], reverse=True)
        rows = [
            *({**row, "kind": "log"} for row in self.logs),
            *({**row, "kind": "metric"} for row in self.metrics),
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
