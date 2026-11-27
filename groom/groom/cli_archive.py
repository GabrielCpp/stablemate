"""The ``groom archive`` verbs and the byte formatting they share with ``groom purge``."""

from __future__ import annotations

from typing import Any


def format_bytes(count: int) -> str:
    value = float(count)
    for unit in ("B", "K", "M", "G"):
        if value < 1024 or unit == "G":
            return f"{value:.0f}{unit}" if unit == "B" else f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.1f}G"


def archive_ls(run: str = "", long: bool = False, as_json: bool = False) -> None:
    """List frozen runs."""
    import json as _json

    from groom import archive

    dirs = archive.archive_dirs()
    if run:
        dirs = [
            path for path in dirs if path.name == run or path.name.startswith(f"{run}-")
        ]
    if not (long or run or as_json):
        for path in dirs:
            print(path.name)
        if not dirs:
            print(f"no archived runs under {archive.archives_root()}.")
        return
    rows: list[dict[str, Any]] = []
    for path in dirs:
        found = archive.manifest(path)
        counts = found.get("rows") or {}
        rows.append(
            {
                "run": path.name,
                "dir": str(path),
                "workflow": found.get("workflow", ""),
                "repo": found.get("repo", ""),
                "branch": found.get("branch", ""),
                "archived_at": found.get("archived_at"),
                "min_ts": found.get("min_ts"),
                "max_ts": found.get("max_ts"),
                "spans": counts.get("span", 0),
                "logs": counts.get("log", 0),
                "metrics": counts.get("metric", 0),
            }
        )
    if as_json:
        print(_json.dumps(rows, indent=2))
        return
    if not rows:
        print(f"no archived runs under {archive.archives_root()}.")
        return
    import datetime as _dt

    print(
        f"{'run':<34} {'archived':<17} {'workflow':<20} {'spans':>8} {'logs':>9} {'metrics':>8}"
    )
    for row in rows:
        stamp = row["archived_at"]
        when = (
            _dt.datetime.fromtimestamp(float(stamp)).strftime("%Y-%m-%d %H:%M")
            if isinstance(stamp, (int, float))
            else "-"
        )
        print(
            f"{str(row['run'])[:34]:<34} {when:<17} {str(row['workflow'])[:20]:<20}"
            f" {row['spans']:>8} {row['logs']:>9} {row['metrics']:>8}"
        )


def archive_show(run: str, limit: int = 0) -> None:
    """Stream one frozen run's ``telemetry.jsonl`` to stdout."""
    from groom import archive

    folder = archive.archive_dir(run)
    if folder is None:
        print(f"no archived run {run} under {archive.archives_root()}.")
        return
    target = folder / archive.TELEMETRY_FILE
    with target.open(encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            if limit and index > limit:
                return
            print(line.rstrip("\n"))


def archive_now(dry_run: bool = False, limit: int = 0, as_json: bool = False) -> None:
    """Run an archival sweep now, instead of waiting for the six-hour tick."""
    import json as _json

    from groom import archive

    result = archive.sweep(limit=limit or archive.RUNS_PER_PASS, dry_run=dry_run)
    if as_json:
        print(_json.dumps(result.as_dict(), indent=2))
        return
    verb = "would archive" if dry_run else "archived"
    print(
        f"{verb} {len(result.archived)} run(s): {result.rows} row(s),"
        f" {format_bytes(result.bytes)} written"
    )
    for name in result.archived[:20]:
        print(f"  {name}")
    if len(result.archived) > 20:
        print(f"  … and {len(result.archived) - 20} more")
    if result.resumed:
        print(
            f"finished {len(result.resumed)} interrupted sweep(s): {', '.join(result.resumed)}"
        )
    if result.failed:
        print(f"{len(result.failed)} run(s) failed:")
        for name, why in result.failed.items():
            print(f"  {name}: {why}")
    remaining = result.pending - len(result.archived)
    if remaining > 0:
        print(f"{remaining} run(s) still pending; the sweep is bounded per pass.")
    if result.held:
        print(
            f"{len(result.held)} run(s) held: still emitting past the retention window,"
            " so neither archived nor pruned."
        )


def archive_status(as_json: bool = False) -> None:
    """What the archive holds, what is waiting for it, and what the last sweep did."""
    import json as _json

    from groom import archive

    report = archive.status()
    if as_json:
        print(_json.dumps(report, indent=2))
        return
    print(f"archives:        {report['root']}")
    print(f"frozen runs:     {report['archived_runs']}")
    print(
        f"pending:         {report['pending']} run(s) past {report['retention_days']:.0f}d"
    )
    print(f"held by activity: {len(report['held_by_activity'])} run(s)")
    for run_id in report["held_by_activity"][:10]:
        print(f"  {run_id}")
    last = report["last_sweep"]
    if last:
        import datetime as _dt

        when = _dt.datetime.fromtimestamp(last["started"]).strftime("%Y-%m-%d %H:%M")
        print(
            f"last sweep:      {when} — {len(last['archived'])} archived,"
            f" {last['rows']} row(s), {format_bytes(last['bytes'])}"
        )
    else:
        print("last sweep:      none in this process")
    print(
        f"every:           {report['every_s'] / 3600:.1f}h, {report['runs_per_pass']} runs/pass"
    )
    print("deletable without an archive:")
    for name, count in sorted(report["unarchived_deletable"].items()):
        print(f"  {name:<26} {count}")
