"""saddlebag command-line entry point: argparse front end that builds a request, routes it and prints the reply; `exec`."""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import threading
from importlib.metadata import version as _pkg_version
from pathlib import Path

from saddlebag import browser, custody, daemon, preference, protocol, route
from saddlebag.custody import CustodyError
from saddlebag.keyring_store import open_door
from saddlebag.models import FIELDS, VALUE_FIELDS, parse_tag
from saddlebag.protocol import DaemonNotRunning, Reply, Request
from saddlebag.route import RouteError
from saddlebag.store import StoreUnavailable
from saddlebag.vault import VaultError, VaultStore

logger = logging.getLogger(__name__)


def _emit(data: object) -> None:
    json.dump(data, sys.stdout, indent=2)
    sys.stdout.write("\n")


def _error(message: str, code: int) -> int:
    print(f"saddlebag: {message}", file=sys.stderr)
    return code


def _ask(verb: str, args: dict[str, object] | None = None) -> Reply | int:
    try:
        reply = route.choose().ask(Request(verb, args or {}))
    except (DaemonNotRunning, StoreUnavailable, RouteError) as exc:
        return _error(str(exc), 1)
    except protocol.ProtocolError as exc:
        return _error(f"the daemon sent an unreadable reply: {exc}", 1)
    if not reply.ok:
        return _error(reply.error or f"{verb} failed", 1)
    return reply


class UsageError(Exception):
    """The command line is malformed. The message is the one line printed."""


def _check_tags(tags: list[str]) -> list[str]:
    for tag in tags:
        try:
            parse_tag(tag)
        except ValueError as exc:
            raise UsageError(str(exc)) from exc
    return tags


def _table(rows: list[list[str]], header: list[str]) -> None:
    widths = [max(len(row[i]) for row in [header, *rows]) for i in range(len(header))]
    for row in [header, *rows]:
        print("  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip())


def _pairs(raw: list[list[str]]) -> str:
    return ",".join(f"{k}={v}" for k, v in raw)


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        custody.refuse_environment()
        if args.keep_token:
            custody.keep(sys.stdin, open_door)
            print("kept the Vault token in the OS keyring", file=sys.stderr)
            return 0
        addr = args.vault_addr or os.environ.get("VAULT_ADDR")
        if not addr:
            return _error("no Vault address: set VAULT_ADDR or pass --vault-addr", 2)
        token = custody.find(sys.stdin, open_door, custody.filed_path())
    except (CustodyError, StoreUnavailable) as exc:
        return _error(str(exc), 2)
    try:
        store = VaultStore(addr, token.value)
    except VaultError as exc:
        return _error(str(exc), 1)
    path = protocol.fit_socket_path(args.socket) if args.socket else protocol.socket_path()
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    try:
        daemon.serve(store, socket_path=path, browser_endpoint=args.cdp, stop=stop, token_source=token.source)
    except OSError as exc:
        return _error(str(exc), 1)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    reply = _ask("list", {"tags": _check_tags(args.tag)})
    if isinstance(reply, int):
        return reply
    if args.json:
        _emit(reply.result)
        return 0
    rows = [
        [s["name"], s["username"] or "", s["var"] or "", ",".join(s["fields"]), _pairs(s["tags"]), s["description"] or ""]
        for s in reply.result["secrets"]
    ]
    _table(rows, ["NAME", "USERNAME", "VAR", "VALUES", "TAGS", "DESCRIPTION"])
    return 0


def cmd_tags(args: argparse.Namespace) -> int:
    reply = _ask("tags", {"tags": _check_tags(args.tag)})
    if isinstance(reply, int):
        return reply
    for pair in reply.result["tags"]:
        print(f"{pair[0]}={pair[1]}")
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    reply = _ask(
        "create",
        {"name": args.name, "username": args.username, "description": args.description, "var": args.var, "tags": _check_tags(args.tag)},
    )
    if isinstance(reply, int):
        return reply
    if args.json:
        _emit(reply.result)
    else:
        print(f"created {args.name}")
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    value = sys.stdin.read().rstrip("\r\n")
    if not value.strip():
        return _error("stdin gave an empty value", 2)
    reply = _ask("set", {"name": args.name, "field": args.field, "value": value})
    if isinstance(reply, int):
        return reply
    print(f"stored {reply.result['characters']} characters as {args.name} {args.field}")
    return 0


def cmd_unset(args: argparse.Namespace) -> int:
    reply = _ask("unset", {"name": args.name, "field": args.field})
    if isinstance(reply, int):
        return reply
    print(f"cleared {args.field} of {args.name}")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    reply = _ask("remove", {"name": args.name})
    if isinstance(reply, int):
        return reply
    print(f"removed {args.name}")
    return 0


def cmd_tag(args: argparse.Namespace) -> int:
    reply = _ask(args.command_name, {"name": args.name, "tags": _check_tags(args.tags)})
    if isinstance(reply, int):
        return reply
    print(f"{'tagged' if args.command_name == 'tag' else 'untagged'} {args.name}")
    return 0


def cmd_fill(args: argparse.Namespace) -> int:
    reply = _ask(
        "fill",
        {
            "name": args.name,
            "field": args.field,
            "selector": args.selector,
            "url_contains": args.url_contains,
            "cdp": args.cdp,
            "min_seconds": args.min_seconds,
        },
    )
    if isinstance(reply, int):
        return reply
    if args.json:
        _emit(reply.result)
        return 0
    extra = f", valid for {reply.result['valid_for_seconds']}s" if "valid_for_seconds" in reply.result else ""
    print(f"filled {reply.result['characters']} characters into {args.selector} on {reply.result['url']}{extra}")
    return 0


def _binding(text: str) -> dict[str, object]:
    var, sep, source = text.partition("=")
    name, _, field = source.partition(".")
    if not sep or not var or not name:
        raise ValueError(f"invalid --env {text!r}: expected VAR=NAME or VAR=NAME.field")
    return {"var": var, "name": name, "field": field or "password"}


def cmd_exec(args: argparse.Namespace) -> int:
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        return _error("exec needs a command after --", 2)
    if not args.tag and not args.env:
        return _error("exec needs at least one --tag or --env", 2)
    try:
        bindings = [_binding(text) for text in args.env]
    except ValueError as exc:
        return _error(str(exc), 2)
    tags = _check_tags(args.tag)
    reply = _ask("env", {"tags": tags, "bindings": bindings})
    if isinstance(reply, int):
        return reply
    values = reply.result.get("values")
    if not isinstance(values, dict):
        return _error("the reply carried no environment", 1)
    try:
        os.execvpe(command[0], command, {**os.environ, **values})
    except OSError as exc:
        return _error(f"cannot run {command[0]}: {exc.strerror or exc}", 127)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    reply = _ask("doctor")
    if isinstance(reply, int):
        return reply
    result = reply.result
    chosen = preference.read()
    result["preference"] = None if chosen is None else {"backend": chosen.backend, "source": chosen.source}
    if args.json:
        _emit(result)
    else:
        route = result["route"]
        if route.startswith("socket "):
            route = f"{route} (daemon {result['version']})"
        print(f"backend: {result['backend']}")
        print(f"route: {route}")
        print(f"preference: {'none (auto)' if chosen is None else f'{chosen.backend} ({chosen.source})'}")
        print(f"store reachable: {'yes' if result['store_reachable'] else 'no'}")
        print(f"secrets without a stored value: {', '.join(result['secrets_without_value']) or 'none'}")
        if result["backend"] != "vault":
            orphans = result["orphan_items"]
            print(f"orphan keyring items: {'not checked on this keyring' if orphans is None else ', '.join(orphans) or 'none'}")
        for item in result["missing_items"]:
            print(f"warning: the catalogue lists a value for {item} that the keyring no longer holds")
        token_source = result.get("token_source")
        if result["backend"] == "vault" and token_source is not None:
            print(f"token source: {token_source}")
            if token_source.startswith("file "):
                print("warning: the Vault token is read from a file; any process of this user can read it. Prefer saddlebag serve --keep-token.")
        if result["vault_token_file"]:
            if result["backend"] == "vault":
                print("warning: ~/.vault-token exists on the daemon's host; any process of this user can read it")
            else:
                print("warning: ~/.vault-token exists; any process of this user can read it")
    healthy = result["store_reachable"] and not result["secrets_without_value"] and not result["missing_items"]
    return 0 if healthy else 1


def _tag_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--tag", action="append", default=[], metavar="K=V", help="match secrets carrying this tag; repeatable")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="saddlebag", description="Fill secrets into browsers and commands without printing them.")
    p.add_argument("--version", action="version", version=f"saddlebag {_pkg_version('stablemate-saddlebag')}")
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging on stderr")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("serve", help="run the daemon; the Vault token comes from stdin, the OS keyring or a 0600 file")
    s.add_argument("--socket", type=Path, metavar="PATH", help="socket to listen on")
    s.add_argument("--vault-addr", metavar="URL", help="Vault address (default $VAULT_ADDR)")
    s.add_argument("--cdp", default=browser.DEFAULT_ENDPOINT, metavar="URL", help="DevTools endpoint, loopback only")
    s.add_argument(
        "--keep-token",
        action="store_true",
        help="read a Vault token from stdin, store it in the OS keyring for later `serve` runs, and exit",
    )
    s.set_defaults(func=cmd_serve)

    ls = sub.add_parser("list", help="list secrets and what they are for")
    _tag_option(ls)
    ls.add_argument("--json", action="store_true")
    ls.set_defaults(func=cmd_list)

    tg = sub.add_parser("tags", help="list the distinct tags of the matching secrets")
    _tag_option(tg)
    tg.set_defaults(func=cmd_tags)

    sec = sub.add_parser("secret", help="create and change secrets")
    ssub = sec.add_subparsers(dest="secret_command", required=True)
    c = ssub.add_parser("create", help="create a secret with no value yet")
    c.add_argument("name")
    c.add_argument("--username")
    c.add_argument("--description")
    c.add_argument("--var", help="environment variable `exec` fills with the password")
    c.add_argument("--tag", action="append", default=[], metavar="K=V")
    c.add_argument("--json", action="store_true")
    c.set_defaults(func=cmd_create)
    st = ssub.add_parser("set", help="store a value read from stdin")
    st.add_argument("name")
    st.add_argument("--field", choices=VALUE_FIELDS, default="password")
    st.set_defaults(func=cmd_set)
    us = ssub.add_parser("unset", help="forget a stored value")
    us.add_argument("name")
    us.add_argument("--field", choices=VALUE_FIELDS, required=True)
    us.set_defaults(func=cmd_unset)
    rm = ssub.add_parser("remove", help="delete a secret and every version")
    rm.add_argument("name")
    rm.set_defaults(func=cmd_remove)
    for verb in ("tag", "untag"):
        t = ssub.add_parser(verb, help=f"{verb} a secret")
        t.add_argument("name")
        t.add_argument("tags", nargs="+", metavar="K=V")
        t.set_defaults(func=cmd_tag, command_name=verb)

    f = sub.add_parser("fill", help="type a value into a browser field over CDP")
    f.add_argument("name")
    f.add_argument("--field", choices=FIELDS, default="password")
    f.add_argument("--selector", required=True, metavar="CSS")
    f.add_argument("--url-contains", metavar="TEXT")
    f.add_argument("--cdp", metavar="URL", help="DevTools endpoint, loopback only (default: the daemon's)")
    f.add_argument("--min-seconds", type=int, default=5, metavar="N")
    f.add_argument("--json", action="store_true")
    f.set_defaults(func=cmd_fill)

    e = sub.add_parser("exec", help="run a command with secrets in its environment")
    _tag_option(e)
    e.add_argument("--env", action="append", default=[], metavar="VAR=NAME[.field]")
    e.add_argument("command", nargs=argparse.REMAINDER, metavar="-- CMD")
    e.set_defaults(func=cmd_exec)

    d = sub.add_parser("doctor", help="check the daemon, Vault and the stored values")
    d.add_argument("--json", action="store_true")
    d.set_defaults(func=cmd_doctor)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(name)s %(levelname)s: %(message)s",
    )
    try:
        raise SystemExit(args.func(args))
    except UsageError as exc:
        raise SystemExit(_error(str(exc), 2)) from exc
    except BrokenPipeError:
        raise SystemExit(0) from None


if __name__ == "__main__":
    main()
