from ostler.book import Field as Wire, Str, request
from ostler.book.screen import Button, Field, Screen, Select, Text


class RunDetail(Screen):
    source = (
        "groom/groom/templates/dashboard.html",
        "groom/groom/assets/dashboard.js",
        "groom/groom/assets/dashboard.js::loadOverview",
        "groom/groom/assets/dashboard.js::retryOverview",
        "groom/groom/assets/dashboard.js::Overview",
        "groom/groom/assets/dashboard.js::ArchiveGone",
        "groom/groom/assets/dashboard.js::markIndexed",
        "groom/groom/assets/dashboard.js::TurnReading",
        "groom/groom/assets/dashboard.js::StepReading",
        "groom/groom/assets/dashboard.js::GateReading",
        "groom/groom/assets/dashboard.js::EntryPane",
        "groom/groom/assets/dashboard.js::StepLogs",
        "groom/groom/assets/dashboard.js::StepNext",
        "groom/groom/assets/dashboard.js::openRow",
        "groom/groom/assets/dashboard.js::loadEntry",
        "groom/groom/assets/dashboard.js::TurnPane",
        "groom/groom/assets/dashboard.js::TurnHead",
        "groom/groom/assets/dashboard.js::PartFold",
        "groom/groom/assets/dashboard.js::ToolRun",
        "groom/groom/assets/dashboard.js::ToolLine",
        "groom/groom/assets/dashboard.js::toolRuns",
        "groom/groom/assets/dashboard.js::runLabel",
        "groom/groom/assets/dashboard.js::fmtToolTime",
        "groom/groom/assets/dashboard.js::missingParts",
        "groom/groom/assets/dashboard.js::wordCount",
        "groom/groom/assets/dashboard.js::flip",
        "groom/groom/assets/dashboard.js::flush",
        "groom/groom/assets/dashboard.js::ActivityTab",
        "groom/groom/assets/dashboard.js::FollowControl",
        "groom/groom/assets/dashboard.js::pauseFollow",
        "groom/groom/assets/dashboard.js::resumeFollow",
        "groom/groom/assets/dashboard.js::arrivals",
        "groom/groom/assets/dashboard.js::newestKey",
        "groom/groom/assets/dashboard.js::keepInView",
        "groom/groom/assets/dashboard.js::moveTimeline",
        "groom/groom/assets/dashboard.js::nextProblem",
        "groom/groom/assets/dashboard.js::goToRow",
        "groom/groom/assets/dashboard.js::timelineView",
        "groom/groom/assets/dashboard.js::orderedKeys",
        "groom/groom/assets/dashboard.js::setQuery",
        "groom/groom/assets/dashboard.js::setItem",
        "groom/groom/assets/dashboard.js::clearFilters",
        "groom/groom/assets/dashboard.js::searchTranscripts",
        "groom/groom/assets/dashboard.js::Marked",
        "groom/groom/assets/dashboard.js::transcriptHit",
        "groom/groom/assets/dashboard.js::setProblems",
        "groom/groom/assets/dashboard.js::openProblems",
        "groom/groom/assets/dashboard.js::showNewestProblem",
        "groom/groom/assets/dashboard.js::ProblemReading",
        "groom/groom/assets/dashboard.js::DetailTabs",
        "groom/groom/assets/dashboard.js::AttentionTile",
        "groom/groom/assets/dashboard.js::toggleSteps",
        "groom/groom/assets/dashboard.js::toggleLogs",
        "groom/groom/assets/dashboard.js::stepCount",
        "groom/groom/assets/dashboard.js::toggleRaw",
        "groom/groom/assets/dashboard.js::loadRaw",
        "groom/groom/assets/dashboard.js::loadOlder",
        "groom/groom/assets/dashboard.js::refreshRaw",
        "groom/groom/assets/dashboard.js::fetchRecords",
        "groom/groom/assets/dashboard.js::RawView",
        "groom/groom/assets/dashboard.js::NowStrip",
        "groom/groom/assets/dashboard.js::AttendLink",
        "groom/groom/assets/dashboard.js::ItemsTile",
        "groom/groom/assets/dashboard.js::eachNote",
        "groom/groom/assets/dashboard.js::NodeTable",
        "groom/groom/assets/dashboard.js::medianCell",
        "groom/groom/assets/dashboard.js::medianHeading",
        "groom/groom/medians.py::node_readings",
        "groom/groom/history.py::comparison",
        "groom/groom/overview.py::run_overview",
        "groom/groom/overview.py::stored_overview",
        "groom/groom/app.py::_archive_overview",
        "groom/groom/archive.py::exact_dir",
        "groom/groom/archive.py::is_indexed",
    )
    route = "/"
    name = "Run detail"
    api = "/api"
    sends = (request("GET", "/api/run/{id}/overview"), request("GET", "/api/archive/{id}/overview"), request("GET", "/api/run/{id}/activity"), request("GET", "/api/state"), request("GET", "/api/settings/attend"))
    root = Text("#detail .detail-head", does="the selected run's header: its state dot, repo and branch, id and state, the note of what the run is doing and, when an attendant has worked on it, the attendant link")
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
        does="the strip above the Overview of a live run: the current node, how long the node has been open, the current turn, step or wait with the node's norm, agent idle and the last beat. Each length counts up every second in the browser with no reload. The norm reads 'a turn here usually takes' or 'this step usually takes'. Under five comparable runs it reads 'no norm yet: N comparable runs'. It shows 'In node' with the time since the node began, except while only the node is known. A wait on the operator reads 'Waiting on you' and any other wait 'Waiting on <kind>', each with the time it has lasted and 'no norm while waiting'",
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
        does="the items done out of the total. The cost divided by the finished items reads '$X per finished item', and a live run with no finished item reads 'none finished yet' with no per-item figure. An ended run with no finished item reads 'no item finished, so no cost per item'. A run with no price reads 'no cost per item without a price'. For an ended run that succeeded and reported a cost, the per-item figure carries its signed percent against the median of the other comparable runs of the workflow and the count in words, '$X per item +N% vs median of M runs'. Under five it says 'only N other comparable <workflow> runs, and it takes 5', and with none 'no other comparable <workflow> run yet, and it takes 5'. A run that did not end in success reads 'not compared:' with its ending in words: 'the run failed', 'the run gave up', 'the run interrupted', 'the run crashed' or 'no ending recorded'. An estimate reads 'est $X per item, not compared:' with the same words for its ending, and 'an estimate has no median' when it succeeded. A live run's tile is unchanged",
    )
    turns_tile = Text(
        "#detail-turns-tile",
        "Agent turns",
        does="the number of agent turns with 'N backend retries' beside it. The retries equal the sum of the Retries column of the flow tree",
    )
    attention_tile = Text(
        "#detail-attention-tile",
        "Attention",
        does="the gates of the run, the time spent waiting on them and the problem count. With any problems, the count is a button that opens the Activity tab with problems on. It counts failed steps, backend retries, failed gate checks and churn alerts, so it is never below the retries, and an answered gate does not count. Its count equals the count on the Activity tab and on the Problems control. Opening it selects the newest problem row",
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
        does="By node: one row per node, merged across the flows and states that reach it, with kind, visits, time, mean, the mean against the node's median, longest visit, cost, cost share and retries. The times equal the leaves of the tree `groom profile` prints. The comparison heading reads 'vs median of N' and under five comparable runs 'vs median: N runs, under five' with the cells blank. A step node has no comparison. On a run that has not ended, the median is the node's norm and a mean 20% or more above it reads 'longer' in words beside the warning color. On an ended run that succeeded, the median is that of the node's mean visit in each other comparable run of the workflow, read from their stored summaries, and the cell reads a bare signed percent in plain ink. An ended run that did not succeed, or whose cost is an estimate or that finished no item, compares no node and its heading reads 'vs median'",
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
    archive_reading = Text(
        "#detail .detail-empty.loading",
        "Reading the archive for the first time",
        does="shown in place of the Overview, announced as a status, the first time an archived run is opened: 'Reading the archive for the first time. This takes a few seconds once, then it is instant.' It carries no problem count and is gone when the Overview appears. Opening the archive again shows no such text, because its index is built, and the Overview arrives in under two seconds",
    )
    archive_gone = Text(
        "#detail .side-state[role=status] h2",
        "This archive's files are gone",
        does="the note above an archived run's tiles when its frozen files are gone: 'The cost and times below come from the run's stored summary. Activity and transcripts cannot be read.' The row stays in History, the Cost, Active time, Items, Agent turns and Attention tiles and the Run facts read from the stored summary, and the breakdown tables are absent",
    )
    archive_unreadable = Text(
        "#detail .side-state[role=alert] h2",
        "This archive could not be read",
        does="the alert shown in place of the Overview when the archive's overview cannot be read: 'Its row in the list comes from the stored summary.' The run's row stays in the list",
    )
    archive_retry = Button(
        "#detail button.retry-overview",
        "Retry now",
        does="in the alert of an archive that could not be read. Pressing it reads the archive again and shows the Overview when the read succeeds",
    )
    activity = Text(
        "#tab-activity",
        "Activity",
        does="the tab of the run's agent turns, directly after Overview, so the tabs read Overview, Activity, Files and Diff, and Overview and Activity alone on a run without a sidecar and on an archived run, which has no Files and no Diff tab. A native run's tab works as a container run's does. The run detail has no Details tab and no telemetry feed. A saved view of the old feed in the browser is ignored, and the detail opens on Overview",
    )
    activity_list = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .tl[role="log"]',
        "Run activity",
        does="the run's moments, oldest first within each group, as a log a screen reader can follow. The list groups them by work item, then by flow pass, then by visit, so an operator finds a moment by where it sits in the run. A run with no work items groups its passes directly under the top level. On a live run it follows: a row that arrives lands at its place and the newest row stays in view, the selected row stays selected and the pane keeps it. An upward scroll pauses the follow, and while paused the rows in view stay where they are and a group that finishes stays open. Scrolling back to the end resumes following and leaves the selection alone, and a scroll that moved nothing does not. After a reconnect the timeline reads the run again and fills the gap. A finished run's turn that the timeline still holds as running reads as ended with no record. Search and the work item selector narrow it together, and clearing them restores it. Problems narrows it to the problem rows, and search and the work item selector apply inside that view",
    )
    activity_item = Button(
        '#detail-panel[aria-labelledby="tab-activity"] .tl button.tl-group',
        "Work item",
        does="the heading of one work item. It names the item, its state in words (running, in progress, done, not counted or count unknown), its active time and its cost, and the same figures stand in the Overview's work item row, written the same way. The time counts agent turns only, which the heading's hint says. It stays in view while the item scrolls. Pressing it, by mouse or by keyboard, opens or closes the item and sets aria-expanded. A finished item starts closed and the item in progress starts open, and the item that holds the selected row stays open",
    )
    activity_pass = Button(
        '#detail-panel[aria-labelledby="tab-activity"] .tl button.tl-flow',
        "Flow pass",
        does="the heading of one pass through a flow, such as 'qa · 1st pass'. It gives the pass's state in words, its time and its cost, and the passes of one flow add up to the flow's row in the Overview, written the same way. It stays in view under its item's heading. Pressing it opens or closes the pass. A finished pass starts closed and the pass holding the running turn starts open",
    )
    activity_fold = Button(
        '#detail-panel[aria-labelledby="tab-activity"] .tl button.ev.steps',
        "steps fold",
        does="a run of passed steps folded into one row that reads 'N steps · time · all passed'. Pressing it shows each step and pressing it again hides them, and aria-expanded follows. A failed step never sits inside a fold. Steps opens and closes every fold at once",
    )
    activity_step = Button(
        '#detail-panel[aria-labelledby="tab-activity"] .tl button.ev.step',
        "step passed",
        does="one passed step, shown once its fold is open. Pressing it reads the step in full in the pane beside the list, with its logs and what came next",
    )
    activity_failed = Button(
        '#detail-panel[aria-labelledby="tab-activity"] .tl button.ev[data-kind="failed"]',
        "failed step",
        does="a step that failed, as its own row between two folds with the mark ✕ and the words 'failed step'. Pressing it reads the step in full in the pane: its head, its whole error, its logs and what came next. A failed agent turn is not a second row: in the whole timeline it is its turn row marked failed, and in the Problems view it is a failed row that opens the turn",
    )
    activity_gate = Button(
        '#detail-panel[aria-labelledby="tab-activity"] .tl button.ev[data-kind="gate"]',
        "operator gate",
        does="a gate the run waited at, as its own row with the mark ? and the words 'operator gate'. A gate that is still open is a row too, keyed as it is once answered, so the row keeps its place when the operator answers. Pressing it reads the gate in full in the pane: its question, its answer and the wait",
    )
    activity_doing = Button(
        '#detail-panel[aria-labelledby="tab-activity"] .tl button.ev[data-kind="doing"]',
        "step running",
        does="the step the run is in now, as its own row with the mark ● and the word 'running'. It reads from the run's live state, because a running step has no stored span yet. Pressing it reads the step in the pane, with its logs so far and 'Nothing yet. This is still running.' in place of what came next",
    )
    activity_retry_row = Button(
        '#detail-panel[aria-labelledby="tab-activity"] .tl button.ev[data-kind="retry"]',
        "backend retry",
        does="a backend retry, as its own row with the mark ! and the words 'backend retry'. It is an agent turn after the first of a visit to a node, which the backend started again, as the Overview's attention tile counts it. It reads '<node> turn started again', with the wait and the attempt only when the backend recorded them. Pressing it reads the retry in the pane",
    )
    activity_churn = Button(
        '#detail-panel[aria-labelledby="tab-activity"] .tl button.ev[data-kind="churn"]',
        "churn alert",
        does="a churn alert, as its own row with the mark ! and the words 'churn alert'. It is the same alert the Overview's attention tile counts, replayed from the stored spans, so it comes back after groom restarts. Its row and its reading in the pane head with 'CHURN', and its accessible name keeps 'churn alert'. Pressing it reads the alert in the pane",
    )
    activity_running = Button(
        '#detail-panel[aria-labelledby="tab-activity"] .tl button.ev.live',
        "running turn",
        does="the turn running now, with the mark ● and the word 'running', as the last row of its pass. Pressing it opens the turn in the pane like any other turn. Its row and the open pane show new messages and tool calls as they arrive. When the run ends the row reads how the turn ended, and its pass and item headings and the run row take its cost"
    )
    activity_follow = Button(
        '#detail-panel[aria-labelledby="tab-activity"] .feedbar button.follow',
        "Following",
        does="on a live run with rows, the control at the right of the timeline's bar. It reads 'Following' with a dot and aria-pressed true while the timeline follows, and 'Paused' with aria-pressed false once the operator scrolls up. Pressing it, by mouse or by keyboard, switches between the two and leaves the selected row alone. While the page's connection is reconnecting or offline it reads 'Not connected' and is disabled. An ended run has no such control, and a run that ends while open loses it",
    )
    activity_pill = Button(
        '#detail-panel[aria-labelledby="tab-activity"] .tl .newpill button.newpill-go',
        "new, back to live",
        does="while paused, the count of rows that arrived since the pause, as 'N new · back to live', or 'N new problems' while Problems narrows the timeline. Its region announces the count politely. Pressing it selects the newest row, opens it in the pane, scrolls it into view, clears the pill, resumes following and puts the focus on the follow control. It goes when the run ends",
    )
    activity_keys = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .feedbar .hint',
        "j k move",
        does="the labels at the right of the timeline's bar, 'j k move' and 'e next problem', each key in a key cap. While the timeline shows and no field, answer box or selector has the focus, j selects the next row and k the previous one, the pane reads the selected row, the row scrolls into view and takes the focus, so Enter and Space act on it. A key that moves to a row out of view pauses a live run's follow, and a key to a row in view keeps it. E selects the next problem after the selection, by the one definition the Overview's attention tile counts, and wraps to the first. It opens the work item, the pass and the fold that hold it. In a run with no problems e reads 'This run has no problems.' and the selection stays. The keys walk only the rows that search and the work item selector leave, and do nothing with a modifier key held",
    )
    activity_search = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .feedbar input.act-search',
        "Search activity",
        does="the field 'Search rows and transcripts…' in the timeline's bar. Typing narrows the timeline at once to the rows whose node, result or name holds the text, with the case ignored and the spaces collapsed. Rows inside folded headings and folds match too, and show. After a quarter second without a keystroke groom also searches the transcripts of this run, and a turn found only there shows with 'in transcript:' and the matching line. J, k and e typed in it are text and move nothing. Clearing it restores the timeline",
    )
    activity_item_filter = Select(
        '#detail-panel[aria-labelledby="tab-activity"] .feedbar select.h-sel',
        "Work item",
        does="the selector at the left of the timeline's bar. Its first option, 'All work items', shows every item. Each other option is a work item of the run, and 'outside any work item' holds the turns with none. Choosing one limits the timeline to it, and the search applies within it. J, k and e pressed while it has the focus move nothing in the timeline. It keeps one width whatever its options",
        options=("All work items",),
    )
    activity_problems = Button(
        '#detail-panel[aria-labelledby="tab-activity"] .feedbar button.fchip.prob',
        "Problems",
        does="the control after 'Only' in the timeline's bar, reading 'Problems' with the count. The count is the one the Overview's attention tile shows: failed steps, backend retries, failed gate checks and churn alerts, and an answered gate is not one. It exposes its state as aria-pressed and works from Enter and Space. Pressing it narrows the timeline to the problem rows under their work item and pass headings, so the number of rows equals the count, and pressing it again restores the whole timeline. A failed agent turn is one failed row that opens its turn. When the selected row is not a problem, pressing it selects and reads the newest problem row and keeps it in view. A selected problem row stays selected, and turning the view off keeps it. Search and the work item selector apply inside the view, and e walks the same rows the view lists",
    )
    activity_tab_count = Text(
        "#detail-activity-count",
        "problems",
        does="on the Activity tab, 'N problem' or 'N problems' in words beside the tab's name when the count is above zero, and nothing at zero. It equals the Problems count of the Overview's attention tile and of the control",
    )
    activity_no_problems = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .tl .detail-empty:has(button.show-all)',
        "This run has no problems.",
        does="in the Problems view of a run with no problems, 'This run has no problems.' announced as a status, and the tab shows no count",
    )
    activity_show_all = Button(
        '#detail-panel[aria-labelledby="tab-activity"] button.show-all',
        "Show the whole timeline",
        does="turns the Problems view off and restores the whole timeline",
    )
    activity_steps = Button(
        '#detail-panel[aria-labelledby="tab-activity"] .feedbar button.fchip.steps-toggle',
        "Steps",
        does="after 'Also show' in the timeline's bar, reading 'Steps' with the number of passed steps the folds hold across the run. It exposes its state as aria-pressed and works from Enter and Space. Pressing it opens every fold into its steps, and pressing it again closes them all. Off at first",
    )
    activity_logs = Button(
        '#detail-panel[aria-labelledby="tab-activity"] .feedbar button.fchip.logs-toggle',
        "Info logs",
        does="after Steps, reading 'Info logs' with the number of logs of the run at info level and above, which is 0 while no pass can hold them. It exposes its state as aria-pressed and works from Enter and Space. Pressing it reads the timeline again with each log as a row at its time inside the pass it belongs to, never splitting a fold, and pressing it again removes them. Turning it on while paused counts no log as an arrival. A debug log is no row and Raw lists it. Off at first",
    )
    activity_raw = Button(
        '#detail-panel[aria-labelledby="tab-activity"] .feedbar button.fchip.raw-toggle',
        "Raw",
        does="at the right of the bar, after the follow control. It exposes its state as aria-pressed and works from Enter and Space. Pressing it replaces the timeline and the pane with the run's stored records, and the bar then holds only the follow control, Metric samples and Raw, with no search, selector, Problems, Steps, Info logs or key labels. While Raw shows, j, k and e move nothing. Pressing it again returns to the timeline with the selected row and its pane as they were",
    )
    activity_metrics = Button(
        '#detail-panel[aria-labelledby="tab-activity"] .feedbar button.fchip.metrics-toggle',
        "Metric samples",
        does="in Raw's bar only, reading 'Metric samples' with how many the run holds once the records are read. It exposes its state as aria-pressed and works from Enter and Space. Off at first. Pressing it reads Raw again with the samples among the records, and pressing it again hides them",
    )
    activity_mark = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .tl mark',
        "match",
        does="the matched text in a row's node, result or transcript line, set as text inside a highlight, so a match reads by its mark and markup in the row shows as written",
    )
    activity_hit = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .tl .w.hit',
        "in transcript",
        does="on a turn found in its transcript, 'in transcript:' and the first line that holds the search, cut to 160 characters around the match and set as text, so markup in it shows as written and no script runs",
    )
    activity_searching = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .tl .search-note:has(.spin)',
        "Searching the transcripts of this run…",
        does="the status while the transcripts of this run are searched. The rows that match the text show meanwhile, and the status goes when the search ends, either way",
    )
    activity_search_failed = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .tl .search-note:has(button.retry-search)',
        "The transcripts of this run could not be searched",
        does="shown when groom could not search the transcripts, with 'These rows match the row text only.' The rows that match the row text stay. It never reads as a search with no match",
    )
    activity_search_retry = Button(
        '#detail-panel[aria-labelledby="tab-activity"] button.retry-search',
        "Retry now",
        does="searches the transcripts again. A search that succeeds adds the transcript matches and clears the failure",
    )
    activity_no_match = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .tl .detail-empty:has(button.clear-search)',
        "Nothing in this run matches",
        does="shown once the transcript search has answered and no row matches, as 'Nothing in this run matches “<text>”.' with the text the operator searched",
    )
    activity_clear = Button(
        '#detail-panel[aria-labelledby="tab-activity"] button.clear-search',
        "Clear the search",
        does="empties the search field and returns the work item selector to 'All work items', which restores the whole timeline",
    )
    activity_turn = Button(
        '#detail-panel[aria-labelledby="tab-activity"] .tl button.ev',
        "turn",
        does="one agent turn: its start time, its node, its one-line result, its duration and its cost. Its accessible name says the node, the state in words (running, finished, failed or ended with no record), when it started, the figures and the result. Pressing it, by mouse or by keyboard, opens the turn in the reading pane beside the list and marks the row with aria-current. The turn reads as it did before the list was grouped",
    )
    activity_no_problem_match = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .tl .detail-empty:has(button.clear-search)',
        "No problems",
        does="in the Problems view, 'No problems in this work item.' with 'Clear the filters' when the work item selector leaves none, and 'No problems match “<text>”.' with 'Clear the search' when the search leaves none",
    )
    turn_head = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .rd > .rd-head',
        "turn header",
        does="for a turn, the node, the work item, a chip that says running, finished, failed or no record, the flow and its pass, the visit, the model, the duration, the cost and the output tokens. A turn outside any flow shows no pass. A running turn shows its elapsed time, reads its cost as landing at the turn's end, and leaves out the figures it cannot know yet. For a backend retry or a churn alert, the head holds the row's name, its work item, its flow and pass and its time, and the body holds what happened",
    )
    retry_reading = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .rd.rd-retry',
        "backend retry",
        does="for a backend retry, the head reads 'backend retry', its work item, the chip 'problem', its pass and its time. Under 'What happened' it says the backend started the node's turn again after the attempt before it ended. It adds that the attempt failed with its reason only when that attempt's span ended in error, and the wait only when the backend recorded one, because the spans hold no other cause. 'What came next' says whether this attempt finished, failed or was started again, with an 'Open that turn' button that opens the retried turn",
    )
    churn_reading = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .rd.rd-churn',
        "CHURN",
        does="for a churn alert, the head reads 'CHURN', its work item, the chip 'problem', its pass and its time. Under 'What happened' it says the node ran N times in a row on the work item with the same labels, so the run may be going round in circles. 'What came next' names the row after the alert, with a button that opens it",
    )
    step_head = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .rd.rd-step > .rd-head',
        "step header",
        does="for a step, its name, its work item, a chip that says failed, running or passed, its flow and pass followed by 'step', its duration (its elapsed time while it runs) and, for a failed step, 'error' with the error class",
    )
    step_error = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .rd.rd-step pre.err-box',
        "Error",
        does="under the mark ✕ and the word 'Error', the failed step's whole error text, as text, so markup in it shows as written and no script runs. A step that passed has none",
    )
    step_logs = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .rd [role="list"][aria-label="Logs from this step"]',
        "Logs from this step",
        does="the step's logs, one line each with its clock time, its level, its node and its message, set as text. They are the logs of the step's node between the span's start and end, because a log row carries no visit. An ERROR or FATAL line reads by its level word and its class as well as its colour. Past 500 lines the earliest go and 'Earlier lines of this step are not shown.' says so",
    )
    step_no_logs = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .rd.rd-step .dim:text("This step recorded no logs.")',
        "This step recorded no logs.",
        does="stands in place of the log list when the step's node logged nothing between the span's start and end",
    )
    step_next = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .rd .at-msg:has(.at-role:text("What came next"))',
        "What came next",
        does="names the row that came after this one in the run. The last row reads 'Nothing came after this.' and a step still running reads 'Nothing yet. This is still running.'. An open gate has none",
    )
    step_open_next = Button(
        '#detail-panel[aria-labelledby="tab-activity"] .rd button.open-next',
        "Open that step",
        does="shown when what came next is a row of the timeline, and named 'Open that step', 'Open that turn' or 'Open that gate' after it. Pressing it opens the work item, the pass and the fold that hold the row, selects the row and keeps it in view",
    )
    gate_head = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .rd.rd-gate > .rd-head',
        "gate header",
        does="for an operator gate, the words 'operator gate', its work item, a chip that says 'waiting' with the wait so far for an open gate, 'answered in' with the wait for an answered gate the run has taken the answer of, 'answered, waiting' with the wait for an answered gate the run has not yet taken the answer of, or 'ended after' with the wait for one that ended without an answer, and its flow, pass and gate file",
    )
    gate_question = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .rd.rd-gate .at-msg:has(.at-role:text("Question"))',
        "Question",
        does="the gate's question as prose, through the same rendering as a message, so markup in it shows as text and no script runs. It reads 'The question could not be read.' when the gate file gave none",
    )
    gate_answer = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .rd.rd-gate .at-msg:has(.at-role:text("Your answer"))',
        "Your answer",
        does="the answer to this asking, read from the gate file. Its label carries the clock time the gate ended only once the run has taken the answer. Before that the pane reads 'Answered. The run has not picked the answer up yet.', and once the run has taken it a gate file with no answer for this asking reads 'The gate file holds no answer for this asking.'. An open gate reads 'Not answered yet. Answer in the box above the tabs.' and holds no answer box of its own, because the box above the tabs is the one place to answer. When the operator answers there, the pane turns to the answered view and the selection stays on the gate. A gate that ended with no answer in its file says so",
    )
    entry_reading = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .rd .detail-empty.loading:text("Reading this step")',
        "Reading this step…",
        does="shown while a step or gate is read, announced as a status, and gone when it appears",
    )
    entry_unreadable = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .rd .act-state:has(button.retry-entry)',
        "The details of this step could not be read",
        does="shown in the pane when the read fails, announced as an alert, with 'The row in the timeline stays.'. The row keeps its one line and stays selected",
    )
    entry_retry = Button(
        '#detail-panel[aria-labelledby="tab-activity"] button.retry-entry',
        "Retry now",
        does="reads the step or gate again. A read that succeeds replaces the failure with the details",
    )
    turn_body = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .rd .rd-body',
        "Turn",
        does="the turn's parts in order, named 'Turn <node>' and scrollable from the keyboard: the notes, then the prompt, the thinking and the note that a backend recorded neither, then the messages, tool lines and folds as the turn ran. The turn opens with the prompt, the thinking and every fold closed, and selecting another turn closes them again. A message reads as prose: its markdown is formatted, raw HTML in it is shown as text, an image becomes its alt text, and the result goes through DOMPurify, so no script runs. A turn whose record could not be matched says its messages and tool calls are not shown. A running turn whose start the live history dropped says its earlier output is not shown",
    )
    turn_tool = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .rd .at-tool-head',
        "tool call",
        does="one tool call on one line, its name and a short summary set as text, so markup in either shows as written. A failed call is read by the failed tool call and its output",
    )
    turn_prompt = Button(
        '#detail-panel[aria-labelledby="tab-activity"] .rd details.prompt > summary',
        "Prompt",
        does="the prompt the agent was given, closed and labelled 'Prompt · N words' with its size. Pressing it, by mouse or by Enter or Space, shows the prompt as prose, and pressing it again hides it. Its open state is exposed as expanded. It is absent when the turn recorded no prompt and when the turn's record could not be matched. It goes through the same rendering as a message, so a script in it does not run",
    )
    turn_thinking = Button(
        '#detail-panel[aria-labelledby="tab-activity"] .rd details.thought > summary',
        "Thinking",
        does="the agent's thinking, closed and labelled 'Thinking'. Pressing it shows the thinking as prose, and pressing it again hides it. Its open state is exposed as expanded. It is absent when the turn recorded no thinking",
    )
    turn_not_recorded = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .rd .at-note:text("did not record")',
        "This backend did not record the prompt or the thinking for this turn.",
        does="sits where the prompt and the thinking would, and names only the part the backend left out: the prompt, the thinking, or both. A running turn, a turn that ended with no record and a turn whose start the live history dropped show no such note",
    )
    turn_tool_run = Button(
        '#detail-panel[aria-labelledby="tab-activity"] .rd button.tool-run',
        "tool calls fold",
        does="three or more successful tool calls in a row folded to one line that counts them by tool, most used first, and gives their summed time, as '2 Read · 1 Grep · 1 Bash · 10s'. One or two successful calls stay as lines. Pressing it shows one line per call and pressing it again folds them, and aria-expanded follows",
    )
    turn_tool_failed = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .rd .at-tool-head.failed',
        "failed tool call",
        does="a failed call as its own line, never inside a fold. It is marked in red and in words, with the mark ✕ and the word 'failed'",
    )
    turn_tool_output = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .rd pre.at-tool-body',
        "Output of <tool>",
        does="the output of a failed call in full, up to 1,000,000 characters, set as text so markup in it shows as written and no script runs. It is named 'Output of <tool>' and scrolls inside its own box from the mouse and the keyboard, and the turn around it stays in place",
    )
    turn_output = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .rd .at-msg.output',
        "Output",
        does="the last assistant message of a finished turn, under the role 'Output' and set apart from the turn's other messages by its colour bar. A running turn has none",
    )
    turn_reading = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .rd .detail-empty.loading',
        "Reading this turn…",
        does="shown while the turn is read, announced as a status, and gone when the turn appears. A turn of an archived run reads 'Reading this turn from the archive…'",
    )
    turn_unreadable = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .rd .act-state:has(button.retry-turn)',
        "This turn could not be read",
        does="shown in the pane when the turn's read fails, announced as an alert, with 'The rest of the run is still here.' The list stays as it was. Only a container run whose records are still to be pulled fails this way, because a finished turn of a native run with no record is unmatched and has nothing to retry",
    )
    turn_retry = Button(
        '#detail-panel[aria-labelledby="tab-activity"] button.retry-turn',
        "Retry now",
        does="reads the turn again, which can succeed once a container run's records are pulled. A read that succeeds replaces the failure with the turn",
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
        does="shown when the timeline holds no turn and no group: 'No activity yet. The first agent turn appears here when it starts.', then 'The run is alive: last beat <time> ago.' for a live run or 'The run has finished.' for an ended one. A run that reported no telemetry reads 'No telemetry for this run. It was recorded before telemetry, or it exports to another collector.', the words the Details tab used, with no bar and no list",
    )
    raw_note = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .rawnote',
        "Every stored record, newest first",
        does="above the list, announced as a status: 'This run has N records', then ', with M metric samples hidden' or ', M of them metric samples', then 'Showing the newest K.' or 'Showing all of them.'",
    )
    raw_list = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .raw[role="log"]',
        "Raw records",
        does="the run's records newest first, a page of 200 at a time, read from the store and not from the 60 the old feed held. A record is a span, a log, a turn event or a churn alert, and transcripts stay in the reading pane. A span is one record, written when it ends, with its duration and its cost where it has one, and a failed span says failed. Each record shows its time, kind, node and text, and a warning or an error is marked by its kind in words as well as color. While following, new records appear at the top. A pause, by scrolling down the list or by the follow control, holds them until the follow resumes",
    )
    raw_older = Button(
        '#detail-panel[aria-labelledby="tab-activity"] .raw button.load-older',
        "Load older records",
        does="at the end of the list while older records remain. Pressing it reads the next 200 below the ones shown and keeps the reader's place. It reads 'Reading older records…' and is disabled while it reads, and 'Older records could not be read.' is announced as an alert when the read fails. The page that holds the oldest record removes it",
    )
    raw_reading = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .detail-empty.loading:text("Reading this run\'s records")',
        "Reading this run's records…",
        does="shown while Raw reads its first page, announced as a status and busy, and gone when the records appear",
    )
    raw_unreadable = Text(
        '#detail-panel[aria-labelledby="tab-activity"] .act-state:has(button.retry-raw)',
        "The records of this run could not be read",
        does="shown when Raw's read fails, announced as an alert, with 'The timeline still works.' Pressing Raw again returns to a working timeline",
    )
    raw_retry = Button(
        '#detail-panel[aria-labelledby="tab-activity"] button.retry-raw',
        "Retry now",
        does="reads Raw again. A read that succeeds replaces the failure with the records",
    )
    attend_link = Button(
        "#detail .detail-head button.attend-link",
        "attendant",
        does="in the run head of a run an attendant has worked, reading 'an attendant is on this run' while one runs and 'last attendant' after, with the reason after a dot when the attendance recorded one. Pressing it opens the Attendant pane on that session",
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
