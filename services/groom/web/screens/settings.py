from ostler.book import request
from ostler.book.screen import Button, Check, Heading, Screen, Text


class Settings(Screen):
    source = ("groom/groom/templates/dashboard.html", "groom/groom/assets/dashboard.js", "groom/groom/settings.py")
    route = "/"
    name = "Settings"
    api = "/api"
    sends = (request("GET", "/api/settings/attend"), request("POST", "/api/settings/attend"))
    root = Text("#settings-pane", does="the settings pane")
    heading = Heading("#settings-pane h2", "Settings", does="the pane's title")
    attend = Check("#setting-attend input[type=checkbox]", "Attend parked and dead runs", does="lets the attendant answer the gates that wait on an operator")
    mode = Text("#setting-attend .setting-mode", "mode", does="the attendant's mode: off, or headless while it answers gates")
    runs = Button(
        "#activitybar .act-btn[data-mode=runs]",
        "Runs",
        does="returns to the run list. While another pane is open and a run is blocked its name reads 'Runs, N blocked runs'",
    )
    runs_badge = Text(
        "#runs-badge",
        "blocked runs",
        does="the number of blocked runs, on the Runs button of the left bar while another pane is open. It counts runs, so a run with two open gates counts once. It is hidden on the run list and when no run is blocked. The number is text, and the button's name carries it for a screen reader",
    )
