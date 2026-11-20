from ostler.book import request
from ostler.book.screen import Screen, Text


class History(Screen):
    source = ("groom/groom/templates/dashboard.html", "groom/groom/assets/dashboard.js")
    route = "/"
    name = "History"
    api = "/api"
    sends = (request("GET", "/api/history"), request("GET", "/api/state"), request("GET", "/api/settings/attend"), request("GET", "/api/run/{id}/overview"))
    root = Text("#history-pane", does="the history pane")
    title = Text("#history-title", "History: runs that ended", does="the pane's title")
    empty = Text("#history .empty-big", does="the line shown when no run ended in the last 30 days")
