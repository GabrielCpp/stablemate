from ostler.book import Field as Wire, Str, request
from ostler.book.screen import Button, Field, Screen, Select, Text


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
        does="the text sent back to that gate. Letters typed in it never trigger a page shortcut, and what was typed survives a live push, a fold of the strip, a send of another gate and a trip to another run and back. The page holds it per run and per gate until it is sent or the gate closes, and a reload drops it. J and k typed in it do not move the run selection",
        takes="answer",
        holds=Wire(Str(), required=False, nullable=True),
    )
    send = Button(
        "#detail form.answer button[type=submit]",
        "Send answer",
        does="sends that gate's answer. When groom takes it, the gate leaves the strip and the tab and its scroll place stay. When groom refuses it, the typed answer stays in the box and the notice says why. The answer is sent the same way on every tab",
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
    activity = Text(
        "#tab-activity",
        "Activity",
        does="the tab of the run's agent turns, directly after Overview, so the tabs read Overview, Activity, Files and Diff, and Overview and Activity alone on a run without a sidecar. A native run's tab works as a container run's does",
    )
    activity_list = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .tl[role="log"]',
        "Run activity",
        does="the run's agent turns, oldest first, as a log a screen reader can follow. A finished run's turn that the timeline still holds as running reads as ended with no record",
    )
    activity_turn = Button(
        '#detail-panel[aria-labelledby="tab-activity"] .tl button.ev',
        "turn",
        does="one agent turn: its start time, its node, its one-line result, its duration and its cost. Its accessible name says the node, the state in words (running, finished, failed or ended with no record), when it started, the figures and the result. Pressing it, by mouse or by keyboard, opens the turn in the reading pane beside the list and marks the row with aria-current",
    )
    turn_head = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .rd > .rd-head',
        "turn header",
        does="the node, the work item, a chip that says running, finished, failed or no record, the flow and its pass, the visit, the model, the duration, the cost and the output tokens. A turn outside any flow shows no pass. A running turn shows its elapsed time, reads its cost as landing at the turn's end, and leaves out the figures it cannot know yet",
    )
    turn_body = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .rd .rd-body',
        "Turn",
        does="the turn's messages and tool calls in order, named 'Turn <node>' and scrollable from the keyboard. A message reads as prose: its markdown is formatted, raw HTML in it is shown as text, an image becomes its alt text, and the result goes through DOMPurify, so no script runs. A turn whose record could not be matched says its messages and tool calls are not shown. A running turn whose start the live history dropped says its earlier output is not shown",
    )
    turn_tool = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .rd .at-tool-head',
        "tool call",
        does="one tool call on one line, its name and a short summary set as text, so markup in either shows as written. A failed call says failed in words and shows its output below the line",
    )
    turn_reading = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .rd .detail-empty.loading',
        "Reading this turn…",
        does="shown while the turn is read, announced as a status, and gone when the turn appears. A turn of an archived run reads 'Reading this turn from the archive…'",
    )
    turn_unreadable = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .rd .act-state:has(button.retry-turn)',
        "This turn could not be read",
        does="shown in the pane when the turn's read fails, announced as an alert, with 'The rest of the run is still here.' The list stays as it was",
    )
    turn_retry = Button(
        '#detail-panel[aria-labelledby="tab-activity"] button.retry-turn',
        "Retry now",
        does="reads the turn again. A read that succeeds replaces the failure with the turn",
    )
    activity_reading = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .detail-empty.loading:text("Reading this run")',
        "Reading this run's activity…",
        does="shown while the run's timeline is read, announced as a status",
    )
    activity_unreadable = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .act-state:has(button.retry-activity)',
        "This run's activity could not be read",
        does="shown when the timeline's read fails, announced as an alert, with 'The Overview tab still works.' It never reads as a run with no activity",
    )
    activity_retry = Button(
        '#detail-panel[aria-labelledby="tab-activity"] button.retry-activity',
        "Retry now",
        does="reads the timeline again. A read that succeeds replaces the failure with the list",
    )
    activity_empty = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .empty-big[role="status"]',
        "No activity yet",
        does="shown when the timeline holds no turn: 'No activity yet. The first agent turn appears here when it starts.', then 'The run is alive: last beat <time> ago.' for a live run or 'The run has finished.' for an ended one. A run that reported no telemetry says so in its place",
    )
    files_tab = Text(
        "#tab-files",
        "Files",
        does="the tab of a live container run whose row says a sidecar is connected, directly before Diff, so the tabs read Overview, Activity, Files and Diff. A native run and an ended run have no Files tab. A container run whose sidecar dropped keeps it, stale, while the page holds a diff for the run, and loses it with no diff held. Selecting a run reads no tree. The first open of Files for a selection reads the tree once. Another tab of the same run and back keeps the tree, the selected file and the collapsed folders, with no new read. Selecting another run resets them. When the run ends while Files is open the tab goes and Overview shows. A gate that opens or is answered while Files is open leaves Files selected, keeps its selected file and its scroll position, and reads no tree again. With more than one checkout, the tab reads the checkout the selector shows.",
    )
    files_tree = Text(
        '#detail-panel[aria-labelledby="tab-files"] .fd-tree',
        "checkout files",
        does="the checkout's files in a folder tree, read from the run's sidecar only. A tree answered by the volume reader is never listed, so it reads as unreadable. A chain of single-child folders is one row. The folders .git, node_modules, __pycache__ and .venv are left out",
    )
    files_folder = Button(
        '#detail-panel[aria-labelledby="tab-files"] .fd-tree .tree-dir-head',
        "folder",
        does="collapses and expands its folder and exposes the state as aria-expanded. A folder the operator collapsed stays collapsed across the tabs of the same run and opens again on another run",
    )
    files_file = Button(
        '#detail-panel[aria-labelledby="tab-files"] .fd-tree .tree-file',
        "file",
        does="reads that file and marks it as the current file. The selected file stays selected across the tabs of the same run",
    )
    files_view = Text(
        '#detail-panel[aria-labelledby="tab-files"] .fd-view[role="region"]',
        "File contents",
        does="the region of the shown file, which scrolls from the keyboard. It is named 'Contents of <path>', and 'File contents' before a file is chosen, when it reads 'Select a file to read it.'",
    )
    files_file_head = Text(
        "#detail-files-file-head",
        "file header",
        does="the path of the shown file, its line count and the language its name implies, as '<path> · N lines · <language>'",
    )
    files_code = Text(
        '#detail-panel[aria-labelledby="tab-files"] .file-pre',
        "file text",
        does="the file's text with syntax coloring, beside a gutter of line numbers that screen readers skip, on a band darker than the pane. The text goes through the page's one highlighting path, so a file or a path cannot inject markup. An empty file reads 'This file is empty.' An empty answer from a sidecar too old to report a failed read says it cannot confirm the file is empty",
    )
    files_reading = Text(
        '#detail-panel[aria-labelledby="tab-files"] .detail-empty.loading',
        "Reading the checkout…",
        does="shown while the tree is read, and 'Reading <path>…' while a file is read, each announced as a status and gone when the reply arrives",
    )
    files_unreadable = Text(
        "#detail-files-unreadable",
        "This checkout could not be read",
        does="shown for a tree the sidecar reported as failed, any sidecar error with no fallback, a rejected fetch or a tree answered by the volume reader, even when that read succeeded. It never reads as a checkout with no files, and it clears when a read succeeds. A checkout with no files reads 'This checkout has no files.', and an empty answer from a sidecar too old to report a failed read says it cannot confirm that",
    )
    file_unreadable = Text(
        "#detail-file-unreadable",
        "could not be read",
        does="'<path> could not be read' with 'This does not mean the file is empty.', shown for a failed file read. It never reads as an empty file, and it clears when a read succeeds",
    )
    files_retry = Button(
        '#detail-panel[aria-labelledby="tab-files"] .side-state button',
        "Retry now",
        does="reads the tree or the file again. It shows only beside a failed read or a stale tab. No control on the tab edits, saves, deletes or refreshes a file",
    )
    files_stale = Text(
        "#detail-files-stale",
        "The sidecar stopped answering",
        does="shown on Files when the sidecar drops while the page holds a diff for the run, with 'The run may still be working.' The tab stays and shows no tree or file: it drops its tree, its selected file and its collapsed folders, and reads the tree again when the sidecar returns, with no file selected. With no diff held the tab goes. After a retry that finds no sidecar it adds 'The sidecar is still not answering.'",
    )
    checkout = Select(
        "#detail-checkout",
        "Checkout",
        does="the selector of a run whose sidecar names more than one checkout, at the right of the tab bar on Files and on Diff and on no other tab. Each option is a checkout's name alone, and the workspace root reads '(workspace root)'. A run with one checkout, or a sidecar that names none, shows no selector and reads its one checkout. A run selected for the first time on the page shows its first checkout. Choosing one reads that checkout's diff, so the size on the Diff tab follows it, and Files reads that checkout's tree and drops the open file and the collapsed folders. The choice holds across Files and Diff, a refresh of the diff and a trip to another run and back. A reload starts again at the first checkout, and a remembered checkout the sidecar no longer names falls back to the first. An unreadable checkout keeps the selector. J and k typed while it has the focus do not move the run selection. Checkout names are text and never markup",
        options=("(workspace root)",),
    )
    sidecar_chip = Text(
        "#run-sidecar-chip",
        "docker · sidecar",
        does="the chip in the header of a container run, 'docker · sidecar' while a connected sidecar backs the run and 'docker' alone without one",
    )
    diff_tab = Text(
        "#tab-diff",
        "Diff",
        does="the tab of a live container run whose row says a sidecar is connected, after Overview, Activity and Files. A native run, an ended run and a container run with no connected sidecar have no Diff tab. It appears within five seconds of the sidecar connecting, with no reload. Selecting the run reads the diff once and a sidecar that connects while its run is selected reads it once more. A run that is not selected costs no read. When the run ends while Diff is open the tab goes and Overview shows. When the sidecar drops the tab stays, marked stale, while the page holds a diff for the run, including a run selected on this page before any diff was read. A run first selected after its sidecar dropped, and any run after a page reload during the drop, has no Diff tab until the sidecar returns, because the kept diff lives in the page. The kept diff is held per checkout and per view, and selecting another run and coming back shows the same kept diff, checkout, time and mark. When the sidecar reconnects the tab reads the diff again and keeps the selected file when it is still in the diff. With more than one checkout, the tab reads the checkout the selector shows. The tab reads the view the Diff view switch shows. A gate that opens or is answered while Diff is open leaves Diff selected, keeps its selected file and its scroll position, and reads no diff again.",
    )
    diff_stale = Text(
        "#detail-diff-stale",
        "stale",
        does="the word 'stale' on the Diff tab in place of the size while the run's sidecar is dropped and the page holds a diff for the run. The tab's name reads 'Diff, stale', so the mark reads without colour. It clears when the sidecar reconnects",
    )
    stale_strip = Text(
        "#detail-stale-strip",
        "The sidecar stopped answering",
        does="a group named 'Sidecar not answering' above the kept diff. It says 'The sidecar stopped answering <age> ago.', with the age ticking on the page's shared second clock and no live region, then 'The run may still be working. This is the diff from <HH:MM:SS>.' After a retry that finds no sidecar it leads with 'The sidecar is still not answering.' and 'It stopped answering <age> ago.', announced once as a status. The kept diff below it keeps its tree, its selected file and its scroll position. It clears when the sidecar reconnects and the diff is read again",
    )
    stale_retry = Button(
        "#detail-stale-strip button",
        "Retry now",
        does="tries the sidecar again, and is disabled while a try is under way. It takes the place of the refresh and the read time while the mark shows. A reply served by the volume reader never replaces the kept diff, its time or its selected file, and never clears the mark. A reply served by the sidecar is a reconnect",
    )
    diff_unread = Text(
        "#detail-diff-unread",
        "was not read",
        does="shown in place of a diff while the mark shows and the page holds no diff for the shown checkout and view. A run with no diff read in the page says 'The sidecar stopped answering before a diff was read'. A checkout or view not read before the drop, in a run where another one was, says 'This view was not read before the sidecar stopped answering'. Each says 'The run may still be working.' and offers Retry now",
    )
    diff_view = Text(
        "#detail-diff-view-switch",
        "Diff view",
        does="the switch on the Diff tab and on no other tab, a group named Diff view with the buttons Uncommitted and Since branch start, one of them pressed. Uncommitted is the default for a run the page has not seen. Each button exposes its pressed state and works from the keyboard, and the pressed one is marked by weight and an underline beside its colour. Choosing a view reads that view of the selected checkout, and the tab's size and tree follow it. The position is held per run in the browser, and it holds across a refresh of the diff, another tab of the run, another checkout, and another run and back. Uncommitted sends the read with no view, so the reply is the one the terminal client gets",
    )
    diff_branch_empty = Text(
        "#detail-diff-branch-empty",
        "This branch has no change since it started",
        does="'This branch has no change since it started at <short commit> on <branch>.', with no count on the tab. A branch whose only change is untracked lists those files and says 'No tracked file has changed since this branch started at <short commit> on <branch>.'",
    )
    diff_branch_missing = Text(
        "#detail-diff-branch-missing",
        "Where this branch started could not be found",
        does="shown when the sidecar finds no default branch ('The checkout has no default branch to compare with.') or a branch sharing no history with it ('This branch shares no history with <branch>.'), each with 'Uncommitted still works.' and a Retry now button. The tab shows no count, and the bar shows no read time or refresh. It clears when a read finds the start",
    )
    diff_branch_default = Text(
        "#detail-diff-branch-default",
        "its default branch",
        does="'This checkout is on <branch>, its default branch, so it has no branch of its own to compare.'",
    )
    diff_branch_old = Text(
        "#detail-diff-branch-old",
        "This view needs a newer sidecar",
        does="shown when the sidecar reports no branch start, with 'Uncommitted still works.' It never shows that sidecar's uncommitted diff as this view",
    )
    diff_size = Text(
        "#detail-diff-count",
        "+N −M",
        does="the lines added and removed by the tracked change, shown on the tab before it is opened. A file git does not track yet adds nothing. A clean checkout, a checkout with only untracked files and an unreadable read show no count. The tab's name carries the size as words, 'Diff, N lines added, M lines removed', so it reads without color. It is the size of the view being read. It gives way to the stale mark while the sidecar is dropped",
    )
    diff_read = Text(
        "#detail-diff-read",
        "read",
        does="when the diff was read, as a clock time and an age that ticks each second, and 'reading…' while a refresh is under way. It is hidden, with the refresh, while Since branch start has no start to compare against, and while the stale mark shows, when the strip gives the read time",
    )
    diff_refresh = Button(
        "#detail button[aria-label=\"Read the diff again\"]",
        "Read the diff again",
        does="reads the diff again and updates the counts. The old content stays on screen while it reads, and the selected file stays selected by its path. It is replaced by the strip's Retry now while the stale mark shows",
    )
    diff_tree = Text(
        "#detail-panel .fd-tree",
        "changed files",
        does="the changed files in a folder tree, each with its lines added and removed. A chain of single-child folders is one row. Files git does not track yet sit in their own group, 'Not tracked by git yet', with no counts. The lines equal what `git diff HEAD` reports for the checkout on Uncommitted, and what `git diff <merge base>` reports on Since branch start, where the merge base is that of the checkout's `HEAD` and its default branch",
    )
    diff_file = Button(
        "#detail-panel .fd-tree .tree-file",
        "changed file",
        does="shows that file's diff and marks it as the current file. The first file of the tree shows when Diff opens. An untracked file says '<path> has no diff because git does not track it yet.'",
    )
    diff_file_head = Text(
        "#detail-diff-file-head",
        "file header",
        does="the path of the shown file, its lines added and removed, the word 'uncommitted', or on Since branch start 'since <short commit> on <branch>' with the full commit and the ref it was found at as its title, and 'new file', 'deleted file' or 'renamed from <old path>' in words",
    )
    diff_changes = Text(
        "#detail-panel .fd-view[role=\"region\"]",
        "Changes",
        does="the shown file's changed lines, rendered by diff2html, which escapes the file's content, so a diff cannot inject markup. The region is named 'Changes in <path>' and scrolls from the keyboard",
    )
    diff_reading = Text(
        "#detail-panel .detail-empty.loading",
        "Reading the diff…",
        does="shown while the first read is under way, announced as a status, and gone when the diff arrives. On Since branch start it reads 'Reading the change since the branch started…'",
    )
    diff_unreadable = Text(
        "#detail-diff-unreadable",
        "This diff could not be read",
        does="shown for a read git failed, a sidecar error or text diff2html cannot parse, with 'This does not mean there are no changes.' It never reads as no changes, and it clears when a read succeeds. On Since branch start it reads 'This view could not be read' with 'This does not mean there is no change.'",
    )
    diff_retry = Button("#detail-diff-unreadable button", "Retry now", does="reads the diff again")
    diff_empty = Text(
        "#detail-panel .fd-view .detail-empty",
        "There are no uncommitted changes in this checkout.",
        does="the words of a clean checkout. A checkout with only untracked files lists them and says 'No tracked file has changed in this checkout.' An empty diff from a sidecar too old to report a failed read says 'This sidecar is too old to report a failed read, so it cannot confirm there are no changes.'",
    )
    rejected = Text("#toasts .toast:has(.t-title:text(\"answer not taken\"))", "toast", does="the notice shown when groom refuses the answer, with the reason groom gave")
