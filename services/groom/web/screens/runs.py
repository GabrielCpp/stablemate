from ostler.book import T, request
from ostler.book.screen import Button, Field, Heading, Screen, Text


class Runs(Screen):
    route = "/"
    name = T("Runs", "Runs")
    first = True
    api = "/api"
    sends = (request("GET", "/api/state"), request("GET", "/api/settings/attend"))
    reached_from = "the page opens on it; the Runs button of the left bar returns to it"
    root = Text("#runs-pane", does="the run list pane")
    heading = Heading("#runs-pane h2", T("Runs", "Runs"), does="the pane's title")
    filter = Field("#runs-pane input[name=q]", T("Filter runs", "Filter runs"), does="narrows the list to the runs whose name, repo, node, task or id holds the text typed")
    run = Button("#runs-list button.row", T("run", "run"), does="one run: its state, repo and branch, short id, what it is doing", per_row=True)
    state = Text("#runs-list button.row .dot", T("state", "state"), does="the run's state, on the row's data-state", per_row=True)
    repo = Text("#runs-list button.row .repo-branch", T("repo", "repo"), does="the repo and branch the run works on, or a dash when it did not say", per_row=True)
    short_id = Text("#runs-list button.row .wid", T("short id", "short id"), does="# and the first four characters of the run's id", per_row=True)
    doing = Text("#runs-list button.row .doing", T("doing", "doing"), does="the gate file a blocked run waits on", per_row=True)
    ended = Text("#runs-list button.row .pulse", T("ended", "ended"), does="the word ended on a run that exited", per_row=True)
    empty = Text("#runs-list .empty", does="the line shown when the list or the filter holds no run")
    statusbar = Text("#statusbar", does="the count of runs per state and of repos and workers")
    settings = Button("#activitybar .act-btn[data-mode=settings]", T("Settings", "Settings"), does="opens the settings pane")
