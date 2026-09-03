"""`inbox` — read and answer the operator's messages to a run.

The counterpart to `control`: `control` tells a *live* run something over its socket;
this reads and writes the run dir directly, so it works on a run that is parked,
finished or dead — an inbox message is advisory, so there is nothing wrong with
replying to one after the run that would have acted on it is long gone. It is also how
a node agent reads its own inbox: this is a command, so it needs no new tool wiring.

`read` and `reply` are the whole surface. Peek and pull collapse into one read, because
a message that disappeared when someone looked at it is a message the next node cannot
act on — nothing here removes a message, only `reply` marks it answered.
"""
from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from workhorse import inbox
from workhorse.cli.target import resolve_target

NAME = "inbox"
HELP = "Read or answer the messages left for a run (read, reply)"

READ = "read"
REPLY = "reply"

INBOX_FILE = "inbox.jsonl"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "action",
        choices=[READ, REPLY],
        help="read: print messages (outstanding by default, --all for every message). "
        "reply: attach an answer to one message by id.",
    )
    parser.add_argument(
        "message_id",
        nargs="?",
        default=None,
        metavar="ID",
        help="For reply, the id of the message being answered.",
    )
    parser.add_argument(
        "text",
        nargs="?",
        default=None,
        metavar="TEXT",
        help="For reply, the reply text.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="For read, print every message, replied or not (default: outstanding only).",
    )
    parser.add_argument(
        "--run",
        default=None,
        metavar="ID|DIR",
        help="Which run: its --run-id, its run-dir name, or a path. Defaults to the "
        "most recent run under --runs-dir that has not finished.",
    )
    parser.add_argument(
        "--runs-dir",
        default=None,
        help="Where run dirs live (default: ./.agents/runs, the same default as `run`).",
    )


def run(args: argparse.Namespace) -> None:
    runs_dir = (
        Path(args.runs_dir).resolve()
        if args.runs_dir
        else (Path.cwd() / ".agents" / "runs").resolve()
    )
    run_dir = resolve_target(args.run, runs_dir, args.registry.name)
    path = run_dir / INBOX_FILE

    if args.action == READ:
        messages = inbox.all_messages(path) if args.all else inbox.outstanding(path)
        if not messages:
            print(f"no {'messages' if args.all else 'outstanding messages'} in {run_dir}")
            return
        for m in messages:
            status = f"replied {m.replied_at}" if m.reply else "outstanding"
            print(f"[{m.id}] {m.at} ({status})")
            print(f"  {m.body}")
            if m.reply:
                print(f"  -> {m.reply}")
        return

    if not args.message_id or args.text is None:
        print("error: reply needs an id and text, e.g. `inbox reply m1 \"go ahead\"`",
              file=sys.stderr)
        sys.exit(1)
    try:
        message = inbox.reply(path, args.message_id, args.text, at=_now())
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"replied to [{message.id}] in {run_dir}")



def _now() -> str:
    return datetime.now(UTC).isoformat()
