from ostler.book import T, request
from ostler.book.screen import Button, Check, Heading, Screen, Text


class Settings(Screen):
    route = "/"
    name = T("Settings", "Settings")
    api = "/api"
    sends = (request("GET", "/api/settings/attend"), request("POST", "/api/settings/attend"))
    reached_from = "the Settings button of the left bar"
    root = Text("#settings-pane", does="the settings pane")
    heading = Heading("#settings-pane h2", T("Settings", "Settings"), does="the pane's title")
    attend = Check("#setting-attend input[type=checkbox]", T("Attend parked and dead runs", "Attend parked and dead runs"), does="lets the attendant answer the gates that wait on an operator")
    mode = Text("#setting-attend .setting-mode", T("mode", "mode"), does="the attendant's mode: off, or headless while it answers gates")
    runs = Button("#activitybar .act-btn[data-mode=runs]", T("Runs", "Runs"), does="returns to the run list")
