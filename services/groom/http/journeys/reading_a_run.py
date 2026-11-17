from datetime import date

from ostler.book import Journey

from ...fixtures import blocked, looking_at, running
from .. import endpoints as e


class ReadingARun(Journey):
    """An operator opens a run that waits on a gate. They read the gate, try to answer it and are told
    the run's workspace cannot be reached, leave the run a message and an empty one, and look at its
    cost, its turns, its records, its transcripts and its files. A run that never reported has
    nothing to show, and its stored telemetry is empty, not missing."""

    def steps(self, today: date):
        run = blocked()
        yield e.PushBlocked(run)
        look = looking_at(run.container_id)
        yield e.ReadOutbox(look)
        yield e.AnswerGate(look.but(file_path=run.file_path, answer="yes"))
        yield e.ReadInbox(look)
        yield e.ReadInbox(look.but(include_all=True))
        yield e.LeaveMessage(look.but(body="hold on"))
        yield e.LeaveMessage(look.but(body=""))
        yield e.ReadOverview(look)
        yield e.ReadActivity(look.but(logs=1))
        yield e.ReadRecords(look.but(limit=20, metrics=1))
        yield e.ReadRecords(look.but(before="later"))
        yield e.SearchRun(look.but(q="deploy"))
        yield e.ReadEntry(look.but(key="step:plan"))
        yield e.ReadTurn(look.but(slug="plan-1"))
        yield e.ReadFiles(look.but(repo="shop"))
        yield e.ReadFile(look.but(repo="shop", path="src/app.py"))
        yield e.ReadFile(look.but(path="Makefile"))
        yield e.ReadDiff(look.but(repo="shop"))
        yield e.ReadDiff(look.but(view="branch"))
        stranger = looking_at()
        yield e.ReadOutbox(stranger)
        yield e.AnswerGate(stranger.but(file_path="gates/approve.md", answer="yes"))
        yield e.LeaveMessage(stranger.but(body="hold on"))
        yield e.PushExited(running(exit_code=0).but(container_id=run.container_id))
        yield e.ReadOutbox(look)
