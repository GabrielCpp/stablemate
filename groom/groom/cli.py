"""Console-script entry points: ``groom`` (host-side dashboard server) and
``groom-sidecar`` (the in-container watcher, invoked from the agent image's
entrypoint before workhorse's own run command).

``sidecar`` is imported lazily inside :func:`sidecar_main` — it pulls in
``inotify_simple``, a Linux-only dependency that the host-side ``groom``
process must never need.
"""

from __future__ import annotations

import argparse
import ipaddress
import sys

# Default to all interfaces so the in-container groom-sidecars can reach the
# host over the docker bridge (host.docker.internal → the bridge gateway on
# Linux, not loopback) with no extra flags. groom has no authentication, so this
# is only appropriate on a trusted machine — a non-loopback bind prints a
# warning (below); pass --host 127.0.0.1 to bind loopback only.
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8787


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, *, allow_non_loopback: bool = False) -> None:
    if not _is_loopback(host) and not allow_non_loopback:
        print(
            f"warning: binding non-loopback host {host!r} — groom has NO authentication and "
            "exposes docker control + gate answers to anything that can reach this address. "
            "This is the default so in-container sidecars can reach it over the docker bridge; "
            "pass --host 127.0.0.1 to bind loopback only, or --allow-non-loopback to silence "
            "this warning. Only run on a trusted network.",
            file=sys.stderr,
        )

    import uvicorn

    from groom.app import create_app

    # uvicorn traps SIGINT/SIGTERM itself, but with the dashboard's persistent
    # /ws websocket held open its graceful shutdown otherwise blocks waiting for
    # that connection to drain — so a single Ctrl+C appears to hang until a
    # second one force-quits. A bounded graceful-shutdown timeout closes lingering
    # connections and exits cleanly on the first Ctrl+C.
    config = uvicorn.Config(
        create_app(),
        host=host,
        port=port,
        log_level="info",
        timeout_graceful_shutdown=3,
    )
    server = uvicorn.Server(config)
    try:
        server.run()
    except KeyboardInterrupt:  # pragma: no cover - only on a racing second signal
        pass


def _format_status(rows: list[dict], now: float) -> str:
    if not rows:
        return (
            "no runs have reported telemetry yet.\n"
            "  Is the run exporting? It needs WORKHORSE_OTEL=1 and the otel extra "
            "installed in the SAME interpreter that runs workhorse."
        )
    lines = []
    for row in rows:
        beat_age = now - row["last_beat_ts"]
        if not row["alive"]:
            verdict = f"DEAD? no heartbeat for {int(beat_age)}s"
        elif row["node_elapsed_s"] > 900:
            verdict = f"alive, but in this node {int(row['node_elapsed_s'] / 60)} min"
        else:
            verdict = "alive"
        lines.append(
            f"{row['run_id']}  [{row['workflow'] or '?'}]\n"
            f"  node    : {row['node'] or '(between nodes)'}"
            f"  ({int(row['node_elapsed_s'])}s in node)\n"
            f"  status  : {verdict}  (last beat {int(beat_age)}s ago)\n"
            f"  agent   : idle {int(row['turn_idle_s'])}s"
            + (f"   gas: {int(row['gas'])}" if row["gas"] is not None else "")
            + (f"\n  run_dir : {row['run_dir']}" if row["run_dir"] else "")
        )
    return "\n".join(lines)


def status(run: str = "", as_json: bool = False) -> None:
    """Print where each live run is right now.

    Reads the same SQLite the dashboard and any agent read — there is no
    privileged view. ``sqlite3 $(groom db-path) "SELECT ..."`` answers anything
    this does not.
    """
    import json as _json
    import time

    from groom import store

    rows = store.live_status(run=run)
    if as_json:
        print(_json.dumps(rows, indent=2))
        return
    print(_format_status(rows, time.time()))


def _format_logs(rows: list[dict]) -> str:
    if not rows:
        return (
            "no log records match.\n"
            "  Runs export logs only with WORKHORSE_OTEL=1, and only script nodes\n"
            "  running in-process emit them (WORKHORSE_SCRIPT_INPROCESS=0 turns that off)."
        )
    import datetime as _dt

    lines = []
    # Oldest-first for reading: the query returns newest-first so the LIMIT keeps
    # the most recent slice, but a log is read forwards.
    for row in reversed(rows):
        stamp = _dt.datetime.fromtimestamp(row["ts"]).strftime("%H:%M:%S")
        node = f" {row['node']}" if row["node"] else ""
        lines.append(f"{stamp} {row['severity']:<7}{node} [{row['logger']}] {row['body']}")
    return "\n".join(lines)


def logs(
    run: str = "",
    node: str = "",
    level: str = "",
    contains: str = "",
    limit: int = 200,
    as_json: bool = False,
) -> None:
    """Print log records for a run.

    The counterpart to ``status``: that says *where* a run is stuck, this says
    what it was saying while it got there. Script nodes only appear here because
    workhorse now runs them in-process — as child processes their stdout was
    consumed whole as JSON and their stderr surfaced only on failure.
    """
    import json as _json

    from groom import store

    rows = store.query_logs(run=run, node=node, level=level, contains=contains, limit=limit)
    if as_json:
        print(_json.dumps(rows, indent=2))
        return
    print(_format_logs(rows))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="groom", description="Local dashboard for workhorse operator gates.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve", help="Run the groom web dashboard.")
    serve_parser.add_argument("--host", default=DEFAULT_HOST)
    serve_parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve_parser.add_argument(
        "--allow-non-loopback",
        action="store_true",
        help="Silence the non-loopback exposure warning (the default host is 0.0.0.0). "
        "groom has no auth — only expose it on a trusted network.",
    )

    status_parser = subparsers.add_parser(
        "status",
        help="Where each live run is right now (open node, node age, agent idleness). "
        "Answers what the trace cannot: an unfinished node has no span.",
    )
    status_parser.add_argument("--run", default="", help="Limit to one run_id.")
    status_parser.add_argument(
        "--json", action="store_true", dest="as_json", help="Machine-readable output."
    )

    logs_parser = subparsers.add_parser(
        "logs",
        help="Log records for a run, including its in-process script nodes.",
    )
    logs_parser.add_argument("--run", default="", help="Limit to one run_id.")
    logs_parser.add_argument("--node", default="", help="Limit to one node id.")
    logs_parser.add_argument(
        "--level", default="", help="Minimum severity (e.g. WARNING shows WARNING+ERROR+FATAL)."
    )
    logs_parser.add_argument("--contains", default="", help="Substring match on the message.")
    logs_parser.add_argument("--limit", type=int, default=200, help="Max records (default 200).")
    logs_parser.add_argument(
        "--json", action="store_true", dest="as_json", help="Machine-readable output."
    )

    subparsers.add_parser("db-path", help="Print the telemetry SQLite path and exit.")

    args = parser.parse_args(argv)
    if args.command == "serve":
        serve(host=args.host, port=args.port, allow_non_loopback=args.allow_non_loopback)
    elif args.command == "status":
        status(run=args.run, as_json=args.as_json)
    elif args.command == "logs":
        logs(
            run=args.run, node=args.node, level=args.level,
            contains=args.contains, limit=args.limit, as_json=args.as_json,
        )
    elif args.command == "db-path":
        from groom import store

        print(store.db_path())


def sidecar_main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="groom-sidecar",
        description="In-container watcher that pushes progress/blocked/exit to the host groom.",
    )
    parser.add_argument(
        "--exit-code",
        type=int,
        default=None,
        help="Send a one-shot 'workflow exited' push with this code and return, instead of watching.",
    )
    parser.add_argument(
        "--query",
        action="store_true",
        help="Print this container's current gate + run state as JSON and exit (host-side pull path).",
    )
    args = parser.parse_args(argv)

    from groom import sidecar

    if args.query:
        import json

        print(json.dumps(sidecar.snapshot()))
        return
    if args.exit_code is not None:
        sidecar.push_exited(args.exit_code)
        return
    sidecar.run()


if __name__ == "__main__":
    main()
