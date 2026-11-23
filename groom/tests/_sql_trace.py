"""One place that records every SQL statement the store runs, on any thread."""
from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from unittest.mock import patch

from groom import store


@contextmanager
def traced_statements() -> Iterator[list[str]]:
    """Yield the list that collects each statement run on a connection the store hands out until the block ends."""
    statements: list[str] = []
    touched: list[sqlite3.Connection] = []

    def tracing(real: Callable[[], sqlite3.Connection]) -> Callable[[], sqlite3.Connection]:
        def wrapper() -> sqlite3.Connection:
            conn = real()
            if not any(conn is seen for seen in touched):
                touched.append(conn)
            conn.set_trace_callback(statements.append)
            return conn

        return wrapper

    with (
        patch.object(store.STORE, "connect", tracing(store.STORE.connect)),
        patch.object(store.STORE, "read_connection", tracing(store.STORE.read_connection)),
    ):
        try:
            yield statements
        finally:
            for conn in touched:
                with suppress(sqlite3.Error):
                    conn.set_trace_callback(None)


def whole_table_scans(call: Callable[[], object]) -> list[str]:
    """Run ``call`` and list each statement it ran whose query plan walks a whole telemetry table with no index."""
    with traced_statements() as statements:
        call()
    conn = store.read_connection()
    scans = []
    for sql in statements:
        if not sql.lstrip().upper().startswith(("SELECT", "WITH")):
            continue
        for row in conn.execute("EXPLAIN QUERY PLAN " + sql):
            if re.match(r"SCAN (spans|charges|turns|metrics|logs)\b(?!.* USING)", row[3]):
                scans.append(f"{row[3]} <- {sql[:80]}")
    return scans
