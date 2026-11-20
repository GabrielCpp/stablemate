from ostler.book import request
from ostler.book.screen import Button, Screen, Text


class Dispatch(Screen):
    source = ("groom/groom/templates/dashboard.html", "groom/groom/assets/dashboard.js")
    route = "/"
    name = "Dispatch"
    api = "/api"
    sends = (request("GET", "/api/dispatch/queues"), request("GET", "/api/state"), request("GET", "/api/settings/attend"), request("GET", "/api/run/{id}/overview"))
    root = Text("#dispatch-pane", does="the dispatch pane")
    empty = Text("#dispatch-queues .empty", does="the line shown when the home config names no dispatch queue")
    new_run = Button("#btn-dispatch-new", "New run", does="opens the form that queues an item; disabled while no queue is configured")
    no_queue = Text("#dispatch-items .detail-empty", does="the line shown until a queue is selected")
