"""The groom process both surfaces run against."""

from __future__ import annotations

import os
import sys
import tempfile

from ostler.book import Fresh, Process, Stack

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, "..", "..", "groom"))
PORT = os.environ.get("GROOM_BOOK_PORT", "18792")
LAUNCH = "from groom.cli import main; main()"


def stack(log_dir: str) -> Stack:
    """The app runs with a `docker` that always fails. groom's startup scan drops every pushed
    run whose container docker does not list, but skips the drop when docker is unreachable,
    so runs the book pushes stay for the whole play."""
    home = tempfile.mkdtemp(prefix="groom-book-")
    bin_dir = os.path.join(home, "bin")
    os.makedirs(bin_dir)
    docker = os.path.join(bin_dir, "docker")
    with open(docker, "w") as handle:
        handle.write("#!/bin/sh\nexit 1\n")
    os.chmod(docker, 0o755)
    env = {
        "PATH": bin_dir + os.pathsep + os.environ.get("PATH", ""),
        "GROOM_DB": os.path.join(home, "groom.sqlite"),
        "HOME": home,
        "XDG_DATA_HOME": os.path.join(home, "data"),
        "XDG_CONFIG_HOME": os.path.join(home, "config"),
        "XDG_STATE_HOME": os.path.join(home, "state"),
    }
    return Stack((Process("api", [sys.executable, "-c", LAUNCH, "serve", "--port", PORT], APP, "Uvicorn running", env),), log_dir, fresh=Fresh(("true",)))
