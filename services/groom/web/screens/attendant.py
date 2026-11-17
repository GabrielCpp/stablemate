from ostler.book import request
from ostler.book.screen import Screen, Text


class Attendant(Screen):
    source = ("groom/groom/templates/dashboard.html", "groom/groom/assets/dashboard.js")
    route = "/"
    name = "Attendant"
    api = "/api"
    sends = (request("GET", "/api/attend/sessions"), request("GET", "/api/state"), request("GET", "/api/settings/attend"), request("GET", "/api/run/{id}/overview"))
    reached_from = "the Attendant button of the left bar"
    root = Text("#attend-pane", does="the attendant pane")
    empty = Text("#attend-list .empty", does="the line shown when groom has sent an agent at no run")
    nothing_selected = Text("#attend-detail .detail-empty", does="the line shown until an attendance is selected")
