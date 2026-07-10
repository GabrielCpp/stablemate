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

    from .app import create_app

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

    args = parser.parse_args(argv)
    if args.command == "serve":
        serve(host=args.host, port=args.port, allow_non_loopback=args.allow_non_loopback)


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

    from . import sidecar

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
