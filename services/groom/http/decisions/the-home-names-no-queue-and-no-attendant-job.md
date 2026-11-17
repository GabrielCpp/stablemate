story: none
date: 2026-11-17
elements: ReadQueues, ReadQueueItems, Enqueue, CancelItem, StopItem, ReadAttendQueue, ReadAttendSessions, ReadAttendSession, StopAttendant
sources: groom/groom/dispatch.py::queue_status, groom/groom/app.py::dispatch_enqueue, groom/groom/attend.py::queue, groom/groom/app.py::attend_session

A dispatch queue exists when the home config names it, and an attendant job exists when a native run's gate waits
on an attendant. The book's groom runs in a home that names no queue and only receives pushes, so there is no queue
and no job. Enqueueing is refused with 404 and the queue named, reading a queue and the queues answers empty, and
cancelling or stopping an item or an attendant answers {ok: false}. An attendance read with no transcript is still
answered, with present false and the command that would resume it.
