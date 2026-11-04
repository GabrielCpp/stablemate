"""Process-group reads and kills shared by the attendant and dispatch runners."""

from __future__ import annotations

import os
import signal
import time
from typing import Any


def kill_group(pid: Any) -> None:
    """Send the group TERM, then KILL, stopping at the first group that is gone."""
    if isinstance(pid, int) and pid > 0:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(pid, sig)
            except OSError:
                break
            time.sleep(0.2)


def alive(pid: Any) -> bool:
    """Whether that pid is still a process."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True
