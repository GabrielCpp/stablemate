from __future__ import annotations

import logging
import sqlite3
from typing import Annotated

from litestar import Request, Response, get, post
from litestar.params import QueryParameter

from groom import (
    alerting,
    alerts,
    otlp,
    store,
)
from groom.native import _project_native_rows
from groom.native_figures import _schedule_figures
from groom.routes.workspace import _push_received, _store_history_batch

logger = logging.getLogger(__name__)


def _real_runs(records: list[dict]) -> list[dict]:
    """Drop records a test process produced, before anything stores or alerts on them."""
    return [r for r in records if not store.is_test_run_dir(str(r.get("run_dir", "")))]


def _truthy(value: str) -> bool:
    """A query flag, read the way a checkbox writes it (`1`, `on`) and the way a hand-typed URL does (`true`, `yes`)."""
    return value.strip().lower() in ("1", "true", "yes", "on")


_RETRY_AFTER_S = "5"


def _store_unavailable() -> Response:
    return Response(
        content=b"",
        status_code=503,
        media_type="application/x-protobuf",
        headers={"Retry-After": _RETRY_AFTER_S},
    )


@post("/v1/traces", include_in_schema=False)
async def otlp_traces(request: Request) -> Response:
    """Standard OTLP/HTTP trace receiver — parse → store → eval rules → broadcast, mirroring push_blocked's shape."""
    body = b""
    try:
        body = await request.body()
        spans = _real_runs(otlp.parse_traces(body))
    except Exception as exc:  # noqa: BLE001 - undecodable payload, whatever the cause → 400
        logger.warning(
            "OTLP traces rejected from %s content-type=%r content-encoding=%r "
            "content-length=%r body-bytes=%d: %s: %s",
            request.client,
            request.headers.get("content-type"),
            request.headers.get("content-encoding"),
            request.headers.get("content-length"),
            len(body),
            type(exc).__name__,
            exc,
        )
        return Response(content=b"", status_code=400, media_type="application/x-protobuf")
    try:
        await _store_history_batch(spans, store.insert_spans)
    except sqlite3.Error:
        return _store_unavailable()
    await alerting._dispatch_alerts(alerts.ingest_spans(spans))
    await _project_native_rows(spans)
    _schedule_figures(spans, stale=True)
    await _push_received(spans)
    return Response(content=b"", media_type="application/x-protobuf", status_code=200)


@post("/v1/metrics", include_in_schema=False)
async def otlp_metrics(request: Request) -> Response:
    """Standard OTLP/HTTP metric receiver."""
    try:
        points = _real_runs(otlp.parse_metrics(await request.body()))
    except Exception:  # noqa: BLE001 - undecodable payload, whatever the cause → 400
        return Response(content=b"", status_code=400, media_type="application/x-protobuf")
    try:
        await _store_history_batch(points, store.insert_metrics, kind="metrics")
    except sqlite3.Error:
        return _store_unavailable()
    await alerting._dispatch_alerts(alerts.ingest_metrics(points))
    await _project_native_rows(points)
    _schedule_figures(points, stale=False)
    await _push_received(points)
    return Response(content=b"", media_type="application/x-protobuf", status_code=200)


@post("/v1/logs", include_in_schema=False)
async def otlp_logs(request: Request) -> Response:
    """Standard OTLP/HTTP log receiver."""
    try:
        records = _real_runs(otlp.parse_logs(await request.body()))
    except Exception:  # noqa: BLE001 - undecodable payload, whatever the cause → 400
        return Response(content=b"", status_code=400, media_type="application/x-protobuf")
    try:
        await _store_history_batch(records, store.insert_logs, kind="logs")
    except sqlite3.Error:
        return _store_unavailable()
    await _push_received(records)
    return Response(content=b"", media_type="application/x-protobuf", status_code=200)


@get("/api/live", include_in_schema=False)
async def api_live(run: Annotated[str, QueryParameter()] = "") -> list[dict]:
    """Where each live run is right now — the rows behind ``groom status``."""
    return alerts.live_status(run=run)
