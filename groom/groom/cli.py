"""Console-script entry points: ``groom`` (host-side dashboard server) and
``groom-sidecar`` (the in-container watcher, invoked from the agent image's
entrypoint before workhorse's own run command).

``sidecar`` is imported lazily inside :func:`sidecar_main` — it pulls in the
filesystem-watch and WebSocket-client machinery that only the in-container
process uses, and the host-side ``groom`` server should not pay for on startup.
(It used to be a portability guard too: the import was ``inotify_simple``, which
does not work off Linux. It is ``watchfiles`` now, so the sidecar runs anywhere
groom does — the laziness is only about import cost.)
"""

from __future__ import annotations

import argparse
import ipaddress
import sys

# Loopback by default: groom has no authentication, and it exposes docker
# control and gate answers to anything that can reach its port — the safe
# default cannot be a warning on the dangerous one. In-container groom-sidecars
# reach the host over the docker bridge (host.docker.internal → the bridge
# gateway on Linux, not loopback), so containerized runs need an explicit
# `--host 0.0.0.0`, which prints the exposure warning below unless
# --allow-non-loopback acknowledges it.
DEFAULT_HOST = "127.0.0.1"
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
            "In-container sidecars need this to reach the host over the docker bridge; "
            "pass --allow-non-loopback to acknowledge it. Only run on a trusted network.",
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
            "  Is the run exporting? A run auto-exports when this collector is reachable,\n"
            "  but it needs the otel extra installed in the SAME interpreter that runs\n"
            "  workhorse — and WORKHORSE_OTEL must not be set to 0/false/no."
        )
    lines = []
    for row in rows:
        beat_age = now - row["last_beat_ts"]
        if not row["alive"]:
            verdict = f"DEAD? no heartbeat for {int(beat_age)}s"
        elif row.get("wait_kind"):
            verdict = (
                f"waiting {row['wait_kind']} for "
                f"{int(row.get('wait_elapsed_s', 0) / 60)} min"
            )
        elif row.get("turn_active"):
            verdict = (
                f"active turn {int(row.get('turn_elapsed_s', 0) / 60)} min, "
                f"idle {int(row['turn_idle_s'])}s"
            )
        elif row["node_elapsed_s"] > 900:
            verdict = f"alive, but in this node {int(row['node_elapsed_s'] / 60)} min"
        else:
            verdict = "alive"
        lines.append(
            f"{row['run_id']}  [{row['workflow'] or '?'}]\n"
            f"  node    : {row['node'] or '(between nodes)'}"
            f"  ({int(row['node_elapsed_s'])}s in node)\n"
            f"  status  : {verdict}  (last beat {int(beat_age)}s ago)\n"
            + (
                f"  agent   : idle {int(row['turn_idle_s'])}s"
                if row.get("turn_active") is not False
                else "  agent   : no active turn"
            )
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
            "  Runs export logs only while telemetry is on, and only script nodes\n"
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


def _format_costs(rows: list[dict]) -> str:
    if not rows:
        return (
            "no agent turns recorded.\n"
            "  Cost and tokens are stamped on agent_turn spans, so a run that has not\n"
            "  yet finished a turn — or ran with telemetry off — has nothing to total."
        )
    header = f"{'node':<28}{'turns':>6}{'/work':>7}{'usd':>9}{'share':>7}{'min':>7}"
    lines = [header, "-" * len(header)]
    for row in rows:
        cost = row["cost_usd"]
        per = row["turns_per_work_id"]
        lines.append(
            f"{row['node'][:27]:<28}{row['turns']:>6}"
            f"{(f'{per:.2f}' if per else '-'):>7}"
            f"{(f'{cost:.2f}' if cost is not None else '-'):>9}"
            f"{row['share'] * 100:>6.1f}%"
            f"{(row['minutes'] or 0):>7.0f}"
        )
    total = sum(row["cost_usd"] or 0.0 for row in rows)
    minutes = sum(row["minutes"] or 0.0 for row in rows)
    turns = sum(row["turns"] for row in rows)
    priced = sum(row["cost_turns"] or 0 for row in rows)
    zeroed = sum(row["zero_cost_turns"] or 0 for row in rows)
    lines.append("-" * len(header))
    lines.append(f"{'total':<28}{turns:>6}{'':>7}{total:>9.2f}{'':>7}{minutes:>7.0f}")
    # Silence here would be a wrong answer, not a missing one. A turn can go unpriced
    # two ways: reporting nothing (a visible gap) or reporting a literal zero while
    # spending tokens (invisible — it sums, so the total looks complete).
    if priced < turns or zeroed:
        backends = sorted({b for row in rows for b in (row["backends"] or "").split(",") if b})
        lines.append("")
        if priced < turns:
            lines.append(
                f"note: {turns - priced} of {turns} turns reported no cost, so usd and"
                f" share cover only the {priced} that did."
            )
        if zeroed:
            lines.append(
                f"note: {zeroed} turn(s) reported a cost of exactly 0 while spending"
                " output tokens. A turn that emitted"
            )
            lines.append(
                "      tokens did not cost nothing — it was not priced. Cost depends on"
                " the provider behind the"
            )
            lines.append(
                "      harness, not the harness: opencode reports real money through"
                " OpenRouter and a flat 0"
            )
            lines.append(
                "      through a subscription provider. (A genuinely free model looks"
                " the same.)"
            )
        lines.append(f"      Backends here: {', '.join(backends) or 'unknown'}.")
    return "\n".join(lines)


def cost(run: str = "", limit: int = 100, as_json: bool = False) -> None:
    """Print per-node agent spend for a run — where the money and the rework went.

    The counterpart to ``status`` and ``logs``: those say where a run is and what it
    said, this says what it cost. ``/work`` is turns per work item (the workflow's
    own ``work_id`` label), which is the rework signal — a node at 1.0 ran once per
    story, a node at 4.6 re-ran three and a half times on average.
    """
    import json as _json

    from groom import store

    rows = store.node_costs(run=run, limit=limit)
    if as_json:
        print(_json.dumps(rows, indent=2))
        return
    print(_format_costs(rows))


def _format_profile(result: dict | None) -> str:
    if result is None:
        return "no telemetry found for that run."
    time_s = result["time_s"]
    work = result["work"]
    waits = ", ".join(
        f"{kind}={seconds / 3600:.2f}h"
        for kind, seconds in time_s["waits_by_kind"].items()
    ) or "none"
    cost = f"${work['cost_usd']:.2f}" if work["cost_usd"] is not None else "-"
    lines = [
        f"{result['run_id']}  [{result['workflow'] or '?'}]",
        "time (disjoint observed wall clock)",
        f"  wall={time_s['wall'] / 3600:.2f}h  agent={time_s['agent'] / 3600:.2f}h"
        f"  deterministic={time_s['deterministic'] / 3600:.2f}h"
        f"  infra={time_s['infra'] / 3600:.2f}h",
        f"  waits={time_s['wait'] / 3600:.2f}h ({waits})"
        f"  resume={time_s['resume_gap'] / 3600:.2f}h"
        f"  unclassified={time_s['unclassified'] / 3600:.2f}h",
        "work",
        f"  visits={work['visits']}  backend_retries={work['backend_retries']}"
        f"  turns={work['turns']}  work_items={work['work_items']}",
        f"  visits/work={work['visits_per_work'] if work['visits_per_work'] is not None else '-'}"
        f"  agent={work['agent_s'] / 3600:.2f}h",
        f"  cost={cost}"
        f"  priced={work['cost_turns']}/{work['turns']}"
        f"  suspect-zero={work['zero_cost_output_turns']}",
    ]
    for title, key in (
        ("attempt groups", "attempt_groups"),
        ("verdict groups", "verdict_groups"),
    ):
        rows = result[key]
        if not rows:
            continue
        lines.append(title)
        for row in rows:
            # The group rows have carried a cost since they were written; printing it is
            # what turns "stalled ×3" from a count into "$41 of stalled", which is the
            # number that decides whether a loop is worth fixing.
            row_cost = f"${row['cost_usd']:.2f}" if row["cost_usd"] is not None else "-"
            lines.append(
                f"  {row['dimension']}={row['value']}  {row['node']}"
                f"  visits={row['visits']}  backend_retries={row['backend_retries']}"
                f"  turns={row['turns']}  agent={row['agent_s'] / 60:.1f}m"
                f"  cost={row_cost}"
            )
    return "\n".join(lines)


def profile(run: str, as_json: bool = False) -> None:
    """Show one run's wall time, workflow visits, backend retries, and verdicts."""
    import json as _json

    from groom import store

    result = store.run_profile(run)
    if as_json:
        print(_json.dumps(result, indent=2))
        return
    print(_format_profile(result))


def purge_tests(dry_run: bool = False, vacuum: bool = True) -> None:
    """Evict telemetry that test runs wrote into the store.

    Producers no longer export from a test process and the receivers drop what
    an older one sends, but neither undoes what is already on disk — and on a
    machine where `groom serve` has been up through a few suite runs that is the
    bulk of the file. Runs are identified by their run dir
    (`store.is_test_run_dir`), so a real run is never guessed at from its name.
    """
    from groom import store

    counts = store.purge_test_runs(dry_run=dry_run, vacuum=vacuum)
    verb = "would remove" if dry_run else "removed"
    if not counts["runs"]:
        print("no test-run telemetry found.")
        return
    print(
        f"{verb} {counts['runs']} test run(s): {counts['spans']} spans,"
        f" {counts['metrics']} metrics, {counts['logs']} logs"
    )
    if not dry_run and vacuum:
        print(f"vacuumed {store.db_path()}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="groom", description="Local dashboard for workhorse operator gates.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve", help="Run the groom web dashboard.")
    serve_parser.add_argument("--host", default=DEFAULT_HOST)
    serve_parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve_parser.add_argument(
        "--allow-non-loopback",
        action="store_true",
        help="Silence the exposure warning printed for a non-loopback --host "
        "(the default binds loopback only). groom has no auth — only expose it "
        "on a trusted network.",
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

    cost_parser = subparsers.add_parser(
        "cost",
        help="Per-node agent spend for a run: where the money and the rework went. "
        "Turns per work item is the rework signal.",
    )
    cost_parser.add_argument("--run", default="", help="Limit to one run_id.")
    cost_parser.add_argument("--limit", type=int, default=100, help="Max nodes (default 100).")
    cost_parser.add_argument(
        "--json", action="store_true", dest="as_json", help="Machine-readable output."
    )

    profile_parser = subparsers.add_parser(
        "profile",
        help="Partition one run's wall time and separate workflow visits from backend retries.",
    )
    profile_parser.add_argument("--run", required=True, help="The run_id to profile.")
    profile_parser.add_argument(
        "--json", action="store_true", dest="as_json", help="Machine-readable output."
    )

    subparsers.add_parser("db-path", help="Print the telemetry SQLite path and exit.")

    purge_parser = subparsers.add_parser(
        "purge-tests",
        help="Delete telemetry written by test runs (run dirs under pytest/temp roots) "
        "and reclaim the space.",
    )
    purge_parser.add_argument(
        "--dry-run", action="store_true", help="Report what would be deleted, delete nothing."
    )
    purge_parser.add_argument(
        "--no-vacuum",
        action="store_false",
        dest="vacuum",
        help="Skip the VACUUM afterwards (faster, but the file keeps its old size).",
    )

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
    elif args.command == "cost":
        cost(run=args.run, limit=args.limit, as_json=args.as_json)
    elif args.command == "profile":
        profile(run=args.run, as_json=args.as_json)
    elif args.command == "db-path":
        from groom import store

        print(store.db_path())
    elif args.command == "purge-tests":
        purge_tests(dry_run=args.dry_run, vacuum=args.vacuum)


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
