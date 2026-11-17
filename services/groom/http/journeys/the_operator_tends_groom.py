from datetime import date

from ostler.book import Journey

from ...fixtures import Settings, asking, looking_at, running
from .. import endpoints as e


class TheOperatorTendsGroom(Journey):
    """An operator checks what groom holds besides the fleet. No run is live, no checkout is
    listed, the attendant has nothing waiting and no log, no dispatch queue is configured, and a
    rescan and a reload find nothing to do. Turning the attendant on changes only its mode."""

    def steps(self, today: date):
        run = running()
        yield e.PushProgress(run)
        yield e.ReadRepos()
        yield e.ReadLive(query=asking())
        yield e.ReadLive(query=asking(run=run.container_id))
        yield e.Refresh()
        yield e.Reload(query=asking())
        yield e.Reload(query=asking(container_id=run.container_id))
        yield e.ReadAttendQueue()
        yield e.ReadAttendSessions()
        yield e.ReadAttendSession(looking_at())
        yield e.StopAttendant(looking_at())
        yield e.SetAttend(Settings(enabled=True))
        yield e.ReadAttendQueue()
        yield e.ReadAttendSessions()
        yield e.SetAttend(Settings(enabled=False))
        yield e.ReadQueues()
        yield e.ReadQueueItems(looking_at().but(queue="nightly"))
        yield e.Enqueue(looking_at().but(queue="nightly"))
        yield e.CancelItem(looking_at().but(queue="nightly", item_id="i1"))
        yield e.StopItem(looking_at().but(queue="nightly", item_id="i1"))
