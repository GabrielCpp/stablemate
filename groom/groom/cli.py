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
            f"refusing to bind non-loopback host {host!r} without --allow-non-loopback "
            "(groom exposes docker control and gate answers with no authentication)",
            file=sys.stderr,
        )
        raise SystemExit(2)

    import uvicorn

    from .app import create_app

    uvicorn.run(create_app(), host=host, port=port, log_level="info")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="groom", description="Local dashboard for workhorse operator gates.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve", help="Run the groom web dashboard.")
    serve_parser.add_argument("--host", default=DEFAULT_HOST)
    serve_parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve_parser.add_argument(
        "--allow-non-loopback",
        action="store_true",
        help="Allow binding a non-loopback host. groom has no auth — only do this on a trusted network.",
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
    args = parser.parse_args(argv)

    from . import sidecar

    if args.exit_code is not None:
        sidecar.push_exited(args.exit_code)
        return
    sidecar.run()


if __name__ == "__main__":
    main()
