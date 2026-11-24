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
        "groom/groom/assets/dashboard.js::HistoryEach",
        "groom/groom/assets/dashboard.js::historyMedian",
        "groom/groom/assets/dashboard.js::HistoryRow",
        "groom/groom/assets/dashboard.js::HistoryNarrowRow",
        "groom/groom/assets/dashboard.js::retryHistoryRun",
        "groom/groom/assets/dashboard.js::setMode",
        "groom/groom/history.py::LABELS",
        "groom/groom/history.py::listing",
        "groom/groom/history.py::discover_archives",
        "groom/groom/history.py::compute_archive",
        "groom/groom/history.py::retry",
        "groom/groom/history.py::keep_archived",
        "groom/groom/archive.py::archive_run",
        "groom/groom/archive.py::_summary_of",
        "groom/groom/medians.py::per_item_costs",
        "groom/groom/medians.py::median_of_others",
        "groom/groom/medians.py::per_workflow",
        "groom/groom/medians.py::compare",
    )
    route = "/"
    name = "History"
    api = "/api"
    sends = (request("GET", "/api/history"), request("GET", "/api/state"), request("GET", "/api/settings/attend"), request("GET", "/api/run/{id}/overview"), request("POST", "/api/history/{id}/retry"))
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
        does="the selector at the right of the bar. It starts on 'Last 30 days'. 'Last 7 days' keeps the runs that ended in the last 7 days, in the browser. 'Everything, archives included' reads History again with the archives, which adds the archived runs to the table and to the totals, and leaving it reads History again without",
        options=("Last 30 days", "Last 7 days", "Everything, archives included"),
    )
    archived_chip = Text(
        "#history table.ht tr.hrow .who .chip",
        "archived",
        does="the word 'archived' after the run id of a run whose files were frozen into an archive, so the marker is a word and never a color. It shows only while the range is 'Everything, archives included'",
    )
    narrow_archived = Text(
        "#history button.row .line1 .chip",
        "archived",
        does="the same word after the run id of an archived run in the narrowed list beside an open run",
    )
    summary_reading = Text(
        "#history table.ht span.dim",
        "reading its summary",
        does="in the Ending cell of an archive whose summary groom has not read yet, with a dash in every figure cell. An archive that carries its summary never shows it. The row fills in on the same page, with no reload, when the one background read of that archive ends, and the totals drop the clause 'still being read' with it. The narrowed list reads the same words",
    )
    summary_unreadable = Text(
        "#history table.ht .unread",
        "could not be read",
        does="in the Ending cell of an archive whose summary could not be read, with a dash in every figure cell and no figure invented. The narrowed list reads the same words and has no retry",
    )
    summary_retry = Button(
        "#history button.retry-summary",
        "Retry now",
        does="beside 'could not be read' in the table, named 'Retry now, <run id>'. Pressing it, by mouse or by Enter or Space, asks groom to read that archive's summary again and does not open the run. The row fills in on the same page when the read succeeds",
    )
    totals = Text(
        "#history .h-sum",
        "Totals",
        does="the strip above the table: the number of runs, the money spent with its clauses (the part that is an estimate, the runs partly priced, the summaries still being read and the summaries that could not be read), the active time and 'N of M ended in success'. Every figure and clause sums the rows the filters leave, and with nothing left they read 0 runs, $0.00 spent and 0m active. With a workflow chosen and rows showing, the strip gains the median cell",
    )
    per_item = Text(
        '#history table.ht th[title^="Per finished item"]',
        "$/item vs median",
        does="the column after Items. Each row's cell reads the run's cost over its finished items, then its signed percent against the median of the other comparable runs of its workflow, with a true minus sign, so the sign carries the meaning without the color. A run that did not end in success, an estimate, and a run with under five other comparable runs read the cost per item with no percent. An estimate reads 'est $X'. A run with no finished item reads '—'. A comparable run is a successful run with a reported cost, a priced turn and a finished item. The median covers every comparable run of the workflow in the store and the archives, whatever the filters and the range, and leaves out the run it judges",
    )
    median = Text(
        '#history .h-sum span[title^="Successful runs of this workflow"]',
        does="the cell the totals gain while a workflow is chosen and rows show: '$X median per <workflow> item, N comparable runs'. Under five comparable runs it reads '—' with 'only N comparable runs, and it takes 5', and with none 'no comparable run yet, and it takes 5'. It counts every comparable run of the workflow, whatever the other filters and the range, and arrives with the list, so choosing a workflow makes no request. With no workflow chosen there is no median",
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
