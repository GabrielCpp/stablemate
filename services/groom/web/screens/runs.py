from ostler.book import Field as Wire, Str, request
from ostler.book.screen import Button, Field, Heading, Screen, Text


class Runs(Screen):
    source = ("groom/groom/templates/dashboard.html", "groom/groom/assets/dashboard.js")
    route = "/"
    name = "Runs"
    first = True
    api = "/api"
    sends = (request("GET", "/api/state"), request("GET", "/api/settings/attend"))
    reached_from = "the page opens on it; the Runs button of the left bar returns to it"
    root = Text("#runs-pane", does="the run list pane")
    heading = Heading("#runs-pane h2", "Runs", does="the pane's title")
    filter = Field("#runs-pane input[name=q]", "Filter runs", does="narrows the list to the runs whose name, repo, node, task or id holds the text typed",
                takes="q", holds=Wire(Str(), required=False, nullable=True))
    run = Button("#runs-list button.row", "run", does="one run: its state, repo and branch, short id, what it is doing", per_row=True)
    state = Text("#runs-list button.row .dot", "state", does="the run's state, on the row's data-state", per_row=True)
    repo = Text("#runs-list button.row .repo-branch", "repo", does="the repo and branch the run works on, or a dash when it did not say", per_row=True)
    short_id = Text("#runs-list button.row .wid", "short id", does="# and the first four characters of the run's id", per_row=True)
    doing = Text("#runs-list button.row .doing", "doing", does="the gate file a blocked run waits on", per_row=True)
    ended = Text("#runs-list button.row .pulse", "ended", does="the word ended on a run that exited", per_row=True)
    empty = Text("#runs-list .empty", does="the line shown when the list or the filter holds no run")
    statusbar = Text("#statusbar", does="the count of runs per state and of repos and workers")
    settings = Button("#activitybar .act-btn[data-mode=settings]", "Settings", does="opens the settings pane")
