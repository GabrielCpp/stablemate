from ostler.book import Field as Wire, Str, request
from ostler.book.screen import Button, Field, Screen, Text


class RunDetail(Screen):
    source = ("groom/groom/templates/dashboard.html", "groom/groom/assets/dashboard.js")
    route = "/"
    name = "Run detail"
    api = "/api"
    sends = (request("GET", "/api/run/{id}/overview"), request("GET", "/api/state"), request("GET", "/api/settings/attend"))
    root = Text("#detail .detail-head", does="the selected run's header: its state dot, repo and branch, id and state")
    repo = Text("#detail .repo-branch", "repo", does="the repo and branch of the run")
    run_id = Text("#detail .run-id", "run id", does="the whole id of the run")
    gate_strip = Text(
        '#detail [role=region][aria-label="Open gates"]',
        "Open gates",
        does="the strip of the gates a run waits on, between the run's header and its tabs and outside the tab's own scrolling region, so no tab's scroll moves it. It lists every open gate of the run, each with its question and its answer box. It appears when a gate opens, and it leaves with the last gate answered, with the tab and its scroll place unchanged. On the Overview the text the operator reads keeps its place on screen while the strip opens, folds or clears. It takes at most half of the pane's height and scrolls inside that",
    )
    waiting = Text(
        "#detail .gate-line b",
        "Waiting on you",
        does="the first words of each gate's block: 'Waiting on you', or 'Waiting on a machine result' for a gate that a machine answers",
    )
    gate_path = Text(
        "#detail .gate-meta",
        "gate path",
        does="the node, the wait so far and the gate file of each gate the run waits on. The folded line keeps the wait so far",
    )
    question = Text(
        "#detail .question",
        "question",
        does="the question of each gate, rendered as sanitized markdown: no script, frame, event handler or javascript: link reaches the page",
    )
    answer = Field(
        "#detail form.answer textarea",
        "Your answer",
        does="the text sent back to that gate. Letters typed in it never trigger a page shortcut, and what was typed survives a live push, a fold of the strip and a send of another gate until it is sent",
        takes="answer",
        holds=Wire(Str(), required=False, nullable=True),
    )
    send = Button(
        "#detail form.answer button[type=submit]",
        "Send answer",
        does="sends that gate's answer. When groom takes it, the gate leaves the strip and the tab and its scroll place stay. When groom refuses it, the typed answer stays in the box and the notice says why",
    )
    collapse = Button(
        "#detail .gate-strip .gate-fold",
        "Collapse",
        does="folds the strip to one line. It sits on the first gate only and keeps every typed answer. The strip stays folded while the same run stays selected, across tabs and live pushes, and opens again on another run or after the run's detail is closed",
    )
    unfold = Button(
        "#detail .gate-strip .gate-unfold",
        "Answer",
        does="the button of the folded line, which shows the start of the first question and the wait so far. It reads 'Show' when no open gate takes an answer. It opens the strip again and puts the focus in the first answer box",
    )
    gates_open = Text(
        "#detail .gate-folded .chip",
        "gates open",
        does="'N gates open' on the folded line when more than one gate waits, so a gate that opens while the strip is folded is counted",
    )
    close = Button("#detail .close-detail", "Close run detail", does="closes the run's detail pane")
    now = Text(
        "#detail .now",
        "Where the run is now",
        does="the strip above the Overview of a live run: the current node, how long the node has been open, the current turn, step or wait with the node's norm, agent idle and the last beat. Each length counts up every second in the browser with no reload. The norm reads 'a turn here usually takes' or 'this step usually takes'. Under five comparable runs it reads 'no norm yet: N comparable runs'. A wait on the operator reads 'Waiting on you' with 'no norm while waiting'",
    )
    past_norm = Text(
        "#detail .now .warn",
        "longer than usual",
        does="the words, beside the warning color, that mark a turn or step lasting longer than its node's norm",
    )
    overview = Text("#tab-overview", "Overview", does="the tab of the run's cost and facts, refreshed in place when a span batch of the run commits, with the strip of a live run above it")
    just_started = Text(
        "#tab-overview",
        "No finished work yet",
        does="the Overview of a run with no finished node: 'No finished work yet' and 'Figures appear when the first node finishes', with no tile and no problem count. The tiles take its place in the same pane, with no reload, once the first node finishes",
    )
    cost_tile = Text(
        "#detail-cost-tile",
        "Cost so far",
        does="the cost of the run. A live run reads 'as of the last finished turn' with its age, 'N of M turns priced' and the cost per active hour, which is the cost over the active time and is left out while the run has no active time. A backend that reports no cost reads '<backend> reports no cost' with 'est $X at list price' when groom can estimate; an ended run reads 'est $X' with 'estimate: this backend reports no cost'. An estimate never appears without that label",
    )
    active_tile = Text(
        "#detail-active-tile",
        "Active time",
        does="the active time of the run with its wall time and its session count beside it, as '<wall> wall, N sessions'. Wall time never appears without the active time. A session is a distinct resume generation, and a run never resumed has one",
    )
    items_tile = Text(
        "#detail-items-tile",
        "Work items",
        does="the items done out of the total. The cost divided by the finished items reads '$X per finished item', and a run with no finished item reads 'none finished yet' with no per-item figure. A run with no price reads 'no cost per item without a price'",
    )
    turns_tile = Text(
        "#detail-turns-tile",
        "Agent turns",
        does="the number of agent turns with 'N backend retries' beside it. The retries equal the sum of the Retries column of the flow tree",
    )
    attention_tile = Text(
        "#detail-attention-tile",
        "Attention",
        does="the gates of the run, the time spent waiting on them and the problem count. With any problems, the count is a button that opens the Activity tab with problems on. It counts failed steps, backend retries, failed gate checks and churn alerts, so it is never below the retries, and an answered gate does not count",
    )
    breakdown_view = Text(
        "[role=group][aria-label=\"Breakdown view\"]",
        "Breakdown view",
        does="the switch above the time and cost table: By flow, By node and, only for a run whose turns carry a work item, By work item. By flow is the default. Each button exposes its pressed state and works from the keyboard. The choice survives a trip to Activity and back and a live refresh, and selecting another run resets it to By flow",
    )
    breakdown_sort = Text(
        "[role=group][aria-label=\"Sort by\"]",
        "Sort by",
        does="the Time and Cost buttons that order the rows of By flow and By node. Each exposes its pressed state. Sorting runs in the browser with no request, ranks by output tokens when the backend reports no cost, and is absent on By work item. The sort survives a trip to Activity and back and a live refresh, and selecting another run resets it to Time",
    )
    flow_table = Text(
        "table[aria-label=\"Time and cost per flow\"]",
        "Time and cost per flow",
        does="By flow: the flow, state and node rows with visits, time, time share, cost, cost share and retries. The rows add up to the run's time and cost",
    )
    node_table = Text(
        "table[aria-label=\"Time and cost per node\"]",
        "Time and cost per node",
        does="By node: one row per node, merged across the flows and states that reach it, with kind, visits, time, mean, the mean against the node's median, longest visit, cost, cost share and retries. The times equal the leaves of the tree `groom profile` prints. The comparison heading reads 'vs median of N' from the successful runs of the same workflow, and under five such runs it reads 'vs median: N runs, under five' with the cells blank. On a live run a mean 20% or more above the median reads 'longer' in words beside the warning color",
    )
    item_table = Text(
        "table[aria-label=\"Time and cost per work item\"]",
        "Time and cost per work item",
        does="By work item: one row per item with its passes, agent time, cost and outcome. Passes are the most turns any one node took for the item, the laps `groom loops` counts, and agent time and cost cover all the item's turns. The item touched last on a live run is marked 'open'. An 'outside any work item' row and a Total make the rows add up to the run's time and cost. The outcome reads done or not counted from the run's progress count, and is blank when no count was reported",
    )
    wall_clock = Text(
        "#detail-wall-clock",
        "Where the wall clock went",
        does="a bar of six segments with a legend that names each one with its duration: Agent turns, Deterministic, Infra, Waits, Unclassified and Stopped between sessions. The segments add up to the wall time, from the first record of the run (a span or a metric) to the last, and Agent turns, Deterministic and Infra add up to the active time of the Active time tile. An instant that more than one kind covers counts once, in this order: stopped between sessions, a wait, agent, infra, deterministic, unclassified. The bar is an image whose accessible name lists every segment with its duration, so the section reads without color",
    )
    models_table = Text(
        "table[aria-label=\"Models\"]",
        "Models",
        does="one row per model with its turns, cost, output tokens and cache read. The cache read is the share of the context tokens read from the cache, with the token count as its tooltip. A model with no priced turn reads 'not reported' and never $0. A model with some priced turns reads 'N of M priced' beside its cost. Turns that name no model fall under '(no model recorded)'. Priced models come first, by cost. The costs add up to the run's cost report",
    )
    facts = Text(
        "#detail-facts",
        "Run",
        does="the run's facts, each with a copy button: Started, Branch, Run id and Run directory when known. A native run adds its Checkout path, and a container run has none, because its workspace volume is not a path on the operator's machine. A run that ended adds Ending and Ended (or Last record), and a run with a pid or gas adds them. The section shows on a run with no finished node too",
    )
    copy = Button(
        "#detail-facts button.copy",
        "Copy run id",
        does="copies the fact beside it and works from Enter and Space. Its name is 'Copy <fact>', such as Copy branch or Copy run directory. A status note beside it reads 'Copied <fact>' for four seconds, or 'Could not copy <fact>' when the browser refuses the write, and a screen reader announces it",
    )
    sessions_table = Text(
        "table[aria-label=\"Sessions\"]",
        "Sessions",
        does="one row per session, the same count as the Active time tile. Each row gives when the session started, its active time, how long the run stayed stopped before the next session and how the session stopped. The ending reads finished, interrupted, reloaded, failed or crashed, with the recorded message or error class after a colon. A session whose root span recorded no ending reads 'no recorded ending'. The last session of a running or blocked run reads 'running', with 'still running' in place of the gap",
    )
    activity = Text("#tab-activity", "Activity", does="the tab of the run's turns")
    sidecar_chip = Text(
        "#run-sidecar-chip",
        "docker · sidecar",
        does="the chip in the header of a container run, 'docker · sidecar' while a connected sidecar backs the run and 'docker' alone without one",
    )
    diff_tab = Text(
        "#tab-diff",
        "Diff",
        does="the tab of a live container run whose row says a sidecar is connected, after Overview, Activity and Files. A native run, an ended run and a container run with no connected sidecar have no Diff tab. It appears within five seconds of the sidecar connecting, with no reload. Selecting the run reads the diff once and a sidecar that connects while its run is selected reads it once more. A run that is not selected costs no read. When the run ends while Diff is open the tab goes and Overview shows. When the sidecar drops the tab stays and reads 'stale', with the last diff kept",
    )
    diff_size = Text(
        "#detail-diff-count",
        "+N −M",
        does="the lines added and removed by the tracked change, shown on the tab before it is opened. A file git does not track yet adds nothing. A clean checkout, a checkout with only untracked files and an unreadable read show no count. The tab's name carries the size as words, 'Diff, N lines added, M lines removed', so it reads without color",
    )
    diff_read = Text(
        "#detail-diff-read",
        "read",
        does="when the diff was read, as a clock time and an age that ticks each second, and 'reading…' while a refresh is under way",
    )
    diff_refresh = Button(
        "#detail button[aria-label=\"Read the diff again\"]",
        "Read the diff again",
        does="reads the diff again and updates the counts. The old content stays on screen while it reads, and the selected file stays selected by its path",
    )
    diff_tree = Text(
        "#detail-panel .fd-tree",
        "changed files",
        does="the changed files in a folder tree, each with its lines added and removed. A chain of single-child folders is one row. Files git does not track yet sit in their own group, 'Not tracked by git yet', with no counts. The lines equal what `git diff HEAD` reports for the checkout",
    )
    diff_file = Button(
        "#detail-panel .fd-tree .tree-file",
        "changed file",
        does="shows that file's diff and marks it as the current file. The first file of the tree shows when Diff opens. An untracked file says '<path> has no diff because git does not track it yet.'",
    )
    diff_file_head = Text(
        "#detail-diff-file-head",
        "file header",
        does="the path of the shown file, its lines added and removed, the word 'uncommitted', and 'new file', 'deleted file' or 'renamed from <old path>' in words",
    )
    diff_changes = Text(
        "#detail-panel .fd-view[role=\"region\"]",
        "Changes",
        does="the shown file's changed lines, rendered by diff2html, which escapes the file's content, so a diff cannot inject markup. The region is named 'Changes in <path>' and scrolls from the keyboard",
    )
    diff_reading = Text(
        "#detail-panel .detail-empty.loading",
        "Reading the diff…",
        does="shown while the first read is under way, announced as a status, and gone when the diff arrives",
    )
    diff_unreadable = Text(
        "#detail-diff-unreadable",
        "This diff could not be read",
        does="shown for a read git failed, a sidecar error or text diff2html cannot parse, with 'This does not mean there are no changes.' It never reads as no changes, and it clears when a read succeeds",
    )
    diff_retry = Button("#detail-diff-unreadable button", "Retry now", does="reads the diff again")
    diff_empty = Text(
        "#detail-panel .fd-view .detail-empty",
        "There are no uncommitted changes in this checkout.",
        does="the words of a clean checkout. A checkout with only untracked files lists them and says 'No tracked file has changed in this checkout.' An empty diff from a sidecar too old to report a failed read says 'This sidecar is too old to report a failed read, so it cannot confirm there are no changes.'",
    )
    rejected = Text("#toasts .toast:has(.t-title:text(\"answer not taken\"))", "toast", does="the notice shown when groom refuses the answer, with the reason groom gave")
