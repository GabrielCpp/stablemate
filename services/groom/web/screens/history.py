from ostler.book import request
from ostler.book.screen import Button, Screen, Select, Text


class History(Screen):
    source = (
        "groom/groom/templates/dashboard.html",
        "groom/groom/assets/dashboard.js",
        "groom/groom/assets/dashboard.js::historyShown",
        "groom/groom/assets/dashboard.js::historySums",
        "groom/groom/assets/dashboard.js::setHistoryFilters",
        "groom/groom/assets/dashboard.js::clearHistoryFilters",
        "groom/groom/assets/dashboard.js::historyScope",
        "groom/groom/assets/dashboard.js::HistoryFilters",
        "groom/groom/assets/dashboard.js::HistoryChoice",
        "groom/groom/assets/dashboard.js::HistoryNoMatch",
        "groom/groom/assets/dashboard.js::HistoryNarrow",
        "groom/groom/assets/dashboard.js::HistoryPane",
        "groom/groom/assets/dashboard.js::setMode",
        "groom/groom/history.py::LABELS",
    )
    route = "/"
    name = "History"
    api = "/api"
    sends = (request("GET", "/api/history"), request("GET", "/api/state"), request("GET", "/api/settings/attend"), request("GET", "/api/run/{id}/overview"))
    root = Text(
        "#history-pane",
        does="the history pane. Its filters, the open run and the narrowed list survive leaving History for another rail tab and coming back, and filtering makes no request except when the range adds or drops the archives",
    )
    title = Text("#history-title", "History: runs that ended", does="the pane's title")
    empty = Text("#history .empty-big", does="the line shown when no run ended in the last 30 days")
    filter = Text(
        "#history .h-top input[type=search]",
        "Filter history",
        does="the box 'Filter by run or repo…' at the left of the bar above the totals. Typing narrows the rows at once to the runs whose id, repo or repo@branch holds the text, with the case ignored and the spaces around it trimmed. It makes no request. While it holds the focus, j, k and e are text and move nothing",
    )
    workflow = Select(
        "#history .h-top select.h-sel[aria-label=Workflow]",
        "Workflow",
        does="the selector of the bar. Its first option, 'All workflows', shows every run, and each other option is a workflow of the runs the list holds, sorted, each once. Choosing one keeps that workflow's runs, and the totals gain the median cost per item of that workflow",
        options=("All workflows",),
    )
    repo = Select(
        "#history .h-top select.h-sel[aria-label=Repo]",
        "Repo",
        does="the selector after Workflow. Its first option, 'All repos', shows every run, and each other option is a repo of the runs the list holds, sorted, each once",
        options=("All repos",),
    )
    ending = Select(
        "#history .h-top select.h-sel[aria-label=Ending]",
        "Ending",
        does="the selector after Repo. Its first option, 'Any ending', shows every run, and the others are every ending in the words and order GET /api/history lists in endings, whether or not a run of the list has it: success, gave up, failed, interrupted, crashed and no ending recorded",
        options=("Any ending", "success", "gave up", "failed", "interrupted", "crashed", "no ending recorded"),
    )
    range = Select(
        "#history .h-top select.h-range",
        "Range",
        does="the selector at the right of the bar. It starts on 'Last 30 days'. 'Last 7 days' keeps the runs that ended in the last 7 days, in the browser. 'Everything, archives included' reads History again with the archives, and leaving it reads History again without",
        options=("Last 30 days", "Last 7 days", "Everything, archives included"),
    )
    totals = Text(
        "#history .h-sum",
        "Totals",
        does="the strip above the table: the number of runs, the money spent with its clauses (the part that is an estimate, the runs partly priced, the summaries still being read and the summaries that could not be read), the active time and 'N of M ended in success'. Every figure and clause sums the rows the filters leave, and with nothing left they read 0 runs, $0.00 spent and 0m active",
    )
    no_match = Text(
        "#history .empty-big:has(button)",
        "No runs match these filters.",
        does="shown in place of the table, and in the narrowed list beside an open run, when the list holds runs and the filters leave none. It differs from the line shown when no run ended in the last 30 days",
    )
    clear = Button(
        "#history .empty-big button",
        "Clear the filters",
        does="under the no-match line. Pressing it resets the text, Workflow, Repo, Ending and Range to their first choices, shows every run of the last 30 days and puts the focus in the filter box",
    )
    scope = Text(
        "#history .h-top.narrow .scope",
        "Filters",
        does="in the narrowed list beside an open run, after the filter box, naming the filters in words: the workflow or 'all workflows', then the repo, the ending and the range when set, such as 'all workflows, failed, last 30 days'. The narrowed list holds the same rows as the table, and the filter box there narrows both",
    )
    close = Button(
        "#history-close",
        "Close run",
        does="the ✕ in the pane head while a run is open. Pressing it returns to the table with every filter as it was",
    )
