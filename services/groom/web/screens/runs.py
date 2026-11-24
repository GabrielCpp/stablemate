from ostler.book import Field as Wire, Str, request
from ostler.book.screen import Button, Field, Heading, Screen, Text


class Runs(Screen):
    source = (
        "groom/groom/templates/dashboard.html",
        "groom/groom/assets/dashboard.js",
        "groom/groom/assets/dashboard.js::ConnectionChip",
        "groom/groom/assets/dashboard.js::RunRow",
        "groom/groom/assets/dashboard.js::noteEndings",
        "groom/groom/assets/dashboard.js::readFailedSince",
        "groom/groom/assets/dashboard.js::markHistorySeen",
        "groom/groom/assets/dashboard.js::paintHistoryBadge",
    )
    route = "/"
    name = "Runs"
    first = True
    api = "/api"
    sends = (request("GET", "/api/state"), request("GET", "/api/settings/attend"))
    root = Text("#runs-pane", does="the run list pane")
    heading = Heading("#runs-pane h2", "Runs", does="the pane's title")
    filter = Field("#runs-pane input[name=q]", "Filter runs", does="narrows the list to the runs whose name, repo, node, task or id holds the text typed",
                takes="q", holds=Wire(Str(), required=False, nullable=True))
    run = Button("#runs-list button.row", "run", does="one run: its state, repo and branch, short id, what it is doing, and once groom hears from the run its cost with priced and total turns, active time and items done. With no field, answer box or selector focused, j selects the next run and k the previous one on every tab of the run detail but Activity, where they move the timeline", per_row=True)
    state = Text("#runs-list button.row .dot", "state", does="the run's state, on the row's data-state", per_row=True)
    repo = Text("#runs-list button.row .repo-branch", "repo", does="the repo and branch the run works on, or a dash when it did not say", per_row=True)
    short_id = Text("#runs-list button.row .wid", "short id", does="# and the first four characters of the run's id", per_row=True)
    doing = Text("#runs-list button.row .doing", "doing", does="the gate file a blocked run waits on", per_row=True)
    ended = Text("#runs-list button.row .pulse", "ended", does="the word ended on a run that exited, and done on a run whose telemetry recorded an ending, whose row also reads how it ended and how long ago", per_row=True)
    empty = Text("#runs-list .empty", does="the line shown when the list or the filter holds no run")
    statusbar = Text("#statusbar", does="the count of runs per state and of repos and workers")
    connection = Text("#statusbar .stat.conn", "Connection", does="the chip in the status bar, its own polite status named 'Connection: <word>'. The word reads live, stale, reconnecting or 'not connected', and the dot beside it is decoration, so the state reads without colour. A socket that closed reads reconnecting for its first minute and 'not connected' after, counted from the moment the open socket closed, so a run of failed reconnects does not reset the clock")
    settings = Button("#activitybar .act-btn[data-mode=settings]", "Settings", does="opens the settings pane")
    history = Button(
        "#activitybar .act-btn[data-mode=history]",
        "History",
        does="opens History. While the badge shows its name reads 'History, N runs failed since you last looked', so the count is in words",
    )
    history_badge = Text(
        "#history-badge",
        "failed runs",
        does="the number of runs that failed, gave up, crashed or were interrupted by a fatal error since History was last opened, on the History button of the left bar, each run counted once. A success and a stop the operator asked for raise none. It is hidden from assistive technology, and the button's name carries the count. It is hidden on History and at zero. Opening History clears it and records now, and leaving History records now again. The time and the run ids live in the browser's local storage and the server is told nothing. A first load with no recorded time records now and shows none. A run that ended before the page loaded counts when it failed after the recorded time, and the count survives a reload",
    )
