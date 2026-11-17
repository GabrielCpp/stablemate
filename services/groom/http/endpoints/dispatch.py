"""What an operator does with a dispatch queue: reads the configured queues and their items,
enqueues one, cancels one before it starts and stops one that runs."""

from ostler.book import Answer, Endpoint, Field, Object, Str

from ...model import actions
from .shapes import DONE, ITEM_ID, ENQUEUE_INPUT, ENQUEUED, QUEUE_ERROR, QUEUE_ITEMS, QUEUES

APP = "groom/groom/app.py::"
DISPATCH = ("groom/groom/dispatch.py", "groom/groom/dispatch_ledger.py", "groom/groom/settings.py")
QUEUE = Field(Str(), does="the queue's name, as the home config names it")
ITEM = Field(ITEM_ID, does="the item's id")


class ReadQueues(Endpoint):
    method = "GET"
    path = "/api/dispatch/queues"
    answers = (Answer(200, QUEUES, "every configured queue with its concurrency and occupancy"),)
    source = (APP + "dispatch_queues", "groom/groom/dispatch.py::queue_status", "groom/groom/dispatch.py::queues", "groom/groom/settings.py")
    does = "Reads every queue the home config names, with its command, its concurrency and what runs in it."
    carries = actions.ReadQueues


class Enqueue(Endpoint):
    method = "POST"
    path = "/api/dispatch/{queue}/items"
    params = Object(queue=QUEUE)
    body = ENQUEUE_INPUT
    answers = (
        Answer(201, ENQUEUED, "{ok: true, item}: the item is queued and spawns when the queue has a free slot"),
        Answer(404, QUEUE_ERROR, "the home config names no such queue"),
    )
    source = (APP + "dispatch_enqueue", "groom/groom/dispatch.py::enqueue", *DISPATCH)
    does = "Queues one item on a configured queue. A queue the config does not name is refused."
    carries = actions.Enqueue


class ReadQueueItems(Endpoint):
    method = "GET"
    path = "/api/dispatch/{queue}/items"
    params = Object(queue=QUEUE)
    answers = (Answer(200, QUEUE_ITEMS, "the queue's items, newest first"),)
    source = (APP + "dispatch_items", "groom/groom/dispatch_ledger.py::dispatch_list")
    does = "Reads a queue's items, newest first, the latest 200."
    carries = actions.ReadQueueItems


class CancelItem(Endpoint):
    method = "DELETE"
    path = "/api/dispatch/{queue}/items/{item_id}"
    params = Object(queue=QUEUE, item_id=ITEM)
    answers = (Answer(200, DONE, "{ok: true} for a pending item cancelled before it spawned, {ok: false} for any other"),)
    source = (APP + "dispatch_delete", "groom/groom/dispatch.py::cancel_pending")
    does = "Cancels a pending item before it ever spawns. The queue named in the path is not consulted."
    carries = actions.DropItem


class StopItem(Endpoint):
    method = "POST"
    path = "/api/dispatch/{queue}/items/{item_id}/stop"
    params = Object(queue=QUEUE, item_id=ITEM)
    answers = (Answer(201, DONE, "{ok: true} when a running item was killed, {ok: false} for any other"),)
    source = (APP + "dispatch_stop", "groom/groom/dispatch.py::stop")
    does = "Kills one item's process and frees its queue slot for the next pending item. The queue named in the path is not consulted."
    carries = actions.DropItem


ALL = (ReadQueues, Enqueue, ReadQueueItems, CancelItem, StopItem)
