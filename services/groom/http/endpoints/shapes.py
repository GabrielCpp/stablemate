"""The bodies groom sends and accepts, each declared once."""

from ostler.book import Bool, Enum, Field, Id, Int, List, Map, Num, Object, Str

from ...model.records import ATTEND_MODES, GATE_STATUS, LIVE, STATES, Item, Job, Run, Session

SESSION_ID = Id(Session, Str(), minted="the book's groom keeps no attendant session, so any name the book makes up is one it has never seen")
JOB_ID = Id(Job, Str(), minted="the book's groom runs no attendant, so any name the book makes up is a job it has never seen")
ITEM_ID = Id(Item, Str(), minted="the book's groom names no dispatch queue, so any name the book makes up is an item it has never seen")
LIVE_RUN = Id(Run, Str(), minted="a live run is one that sends telemetry, which the book cannot send, so any name the book makes up is a run it has never seen")
RUN_ID = Id(Run, Str(), minted="groom keeps every run it was ever told of and is never wiped, so a run id must be new to it")

ERROR = Object(
    "Error",
    status_code=Field(Int()),
    detail=Field(Str(), does="the reason, as the framework words it"),
    extra=Field(
        List(Object("Problem", message=Field(Str()), key=Field(Str()), source=Field(Str()))),
        required=False,
        does="one entry per field the framework refused, present on a validation failure only",
    ),
)

SERVER_ERROR = Object("ServerError", status_code=Field(Int()), detail=Field(Str(), does="the framework's words for an unhandled error"))

ACK = Object("Ack", ok=Field(Bool(), does="true when groom took the push, false when it lacked what it needs to know the run"))

OPAQUE_CLOCK = "the dashboard fills it from run telemetry, which a push never carries"

PROGRESS = Object(
    "Progress",
    container_id=Field(RUN_ID, required=False, does="the run's container id; only its first 12 characters count"),
    name=Field(RUN_ID, required=False, does="the run's display name; a new run without one shows its container id"),
    repo_name=Field(Str(classes={"a plain name": "acme-api", "a name with a slash": "acme/api"}), required=False),
    repo_branch=Field(Str(classes={"a plain branch": "main", "a branch with a slash": "feat/login"}), required=False),
    current_node=Field(Str(classes={"a node name": "build", "a node name with a dash": "write-tests"}), required=False, does="the node the run is in"),
)

BLOCKED = Object(
    "Blocked",
    container_id=Field(RUN_ID, required=False),
    file_path=Field(Str(classes={"an absolute path": "/work/gates/ask.md", "a relative path": "gates/ask.md"}), required=False, does="the gate file the run waits on; one gate per path"),
    question=Field(Str(classes={"a short question": "Ship it?", "a question with a line break": "Ship it?\nYes or no."}), required=False, does="what the run asks the operator"),
    name=Field(RUN_ID, required=False),
    repo_name=Field(Str(classes={"a plain name": "acme-api", "a name with a slash": "acme/api"}), required=False),
    repo_branch=Field(Str(classes={"a plain branch": "main", "a branch with a slash": "feat/login"}), required=False),
)

EXITED = Object(
    "Exited",
    container_id=Field(RUN_ID, required=False),
    exit_code=Field(Int(), required=False, does="the process exit code"),
    name=Field(RUN_ID, required=False),
    repo_name=Field(Str(classes={"a plain name": "acme-api", "a name with a slash": "acme/api"}), required=False),
    repo_branch=Field(Str(classes={"a plain branch": "main", "a branch with a slash": "feat/login"}), required=False),
)

ROW = Object(
    "Row",
    id=Field(RUN_ID, does="the run's container id"),
    run_id=Field(RUN_ID),
    name=Field(RUN_ID),
    repo=Field(Str(), does="repo name at branch, the repo name alone, or a dash"),
    row_id=Field(Id(Run, Str(), strangers="the label is cut from the container id, so it names no run by itself"), opaque="the first four characters of the container id, which carries the minted suffix"),
    type=Field(Str()),
    type_hue=Field(Int()),
    state=Field(Enum(STATES)),
    live=Field(Enum(LIVE)),
    live_label=Field(Str()),
    silence_s=Field(Num()),
    last_seen_ts=Field(Num(), opaque="the moment of the run's last signal, which the clock decides"),
    telemetry_age_s=Field(Num()),
    node=Field(Str()),
    node_elapsed_s=Field(Num()),
    wait_kind=Field(Str()),
    wait_elapsed_s=Field(Num()),
    turn_active=Field(Bool(), nullable=True, does=OPAQUE_CLOCK),
    turn_elapsed_s=Field(Num()),
    turn_idle_s=Field(Num()),
    mini=Field(Str()),
    clock=Field(Map(Str()), nullable=True, does=OPAQUE_CLOCK),
    activity=Field(Str()),
    doing=Field(Str(), does="the first gate path, else empty"),
    question=Field(Str()),
    gate_path=Field(Str(), does="the first gate path in path order"),
    gate_count=Field(Int()),
    exit_code=Field(Int(), nullable=True),
    exit_hint=Field(Str(), does="'exited N' once the run is finished and reported a code"),
    pid=Field(Int(), nullable=True),
    native=Field(Bool()),
    sidecar=Field(Bool()),
    figures=Field(Map(Str()), nullable=True),
    ended=Field(Map(Str()), nullable=True),
    rank=Field(Int(), does="blocked 0, running 2, finished 3; the fleet is ordered by rank, then name"),
)

ALERT = Object(
    "Alert",
    run_id=Field(RUN_ID),
    event=Field(Enum(("blocked", "ended"))),
    node=Field(Str()),
    question=Field(Str(), does="the question as the run pushed it"),
    gate_path=Field(Str()),
    terminal=Field(Str()),
    message=Field(Str()),
)

COUNTS = Object("Counts", running=Field(Int()), blocked=Field(Int()), idle=Field(Int()), finished=Field(Int()))
STATUS = Object("Status", counts=Field(COUNTS), repos=Field(Int()), workers=Field(Int()))
STORE_HEALTH = Object(
    "StoreHealth",
    ok=Field(Bool()),
    path=Field(Str()),
    last_ok_ts=Field(Num()),
    reopens=Field(Int()),
    failures=Field(Int()),
    last_error=Field(Str()),
    last_error_ts=Field(Num()),
    last_write_ts=Field(Num()),
    last_prune_ts=Field(Num()),
    wal_bytes=Field(Int()),
    last_checkpoint_busy=Field(Int()),
)
ATTEND_SUMMARY = Object(
    "AttendSummary",
    mode=Field(Enum(ATTEND_MODES)),
    by_run=Field(Map(Str()), opaque="the attendant's jobs belong to the whole environment"),
    rev=Field(Num(), opaque="counts every change the attendant has seen"),
    count=Field(Int(), opaque="counts the jobs of the whole environment"),
)

REVS = Object(
    "Revisions",
    dispatch=Field(Int(), opaque="counts the changes to the dispatch queues since the server started"),
    history=Field(Int(), opaque="counts the changes to the history since the server started"),
)

FLEET = Object(
    "Fleet",
    type=Field(Str()),
    ts=Field(Num(), opaque="the server's clock"),
    v=Field(Int(), opaque="counts the fleet frames the server has sent since it started"),
    scanning=Field(Bool(), opaque="a discovery scan may be running"),
    runs=Field(List(ROW), does="every run the filter matches, blocked first, then running, then finished, each by name"),
    attention=Field(List(ALERT), does="a blocked event per gate and an ended event per finished run; never filtered by the query"),
    status=Field(STATUS, opaque="counts every run of the environment"),
    store=Field(STORE_HEALTH, opaque="the state of the environment's database"),
    attend=Field(ATTEND_SUMMARY),
    revs=Field(REVS, opaque="counts the changes of the whole environment"),
)

GATE = Object(
    "Gate",
    file_path=Field(Str()),
    question=Field(Str(), does="the latest question of the gate file, trimmed"),
    preview=Field(Str(), does="the first line with content, without its markdown lead-in, at most 140 characters"),
    status=Field(Enum((GATE_STATUS,))),
    kind=Field(Str()),
)

RUNNING = Object(
    "RunningNode",
    node=Field(Str()),
    elapsed_s=Field(Num()),
    wait_kind=Field(Str()),
    wait_elapsed_s=Field(Num()),
    since_ts=Field(Num(), opaque="the server's clock when the run was first seen"),
    node_since_ts=Field(Num(), opaque="the server's clock when the node was first seen"),
)

STRIP = Object(
    "Strip",
    node=Field(Str()),
    kind=Field(Str()),
    wait_kind=Field(Str()),
    started_ts=Field(Num(), opaque="the server's clock"),
    node_since_ts=Field(Num(), opaque="the server's clock"),
    idle_since_ts=Field(Num(), nullable=True),
    beat_ts=Field(Num(), nullable=True),
    norm=Field(Num(), nullable=True),
)

HEAD = Object(
    "Head",
    id=Field(RUN_ID),
    handle=Field(RUN_ID, does="the first 12 characters of the container id"),
    state=Field(Enum(STATES)),
    type=Field(Str()),
    type_hue=Field(Int()),
    repo=Field(Str()),
    live=Field(Enum(LIVE)),
    live_label=Field(Str()),
    last_seen_ts=Field(Num(), opaque="the moment of the run's last signal, which the clock decides"),
    node=Field(Str()),
    pid=Field(Int(), nullable=True),
    cli=Field(Str()),
    exit_hint=Field(Str()),
    exit_ok=Field(Bool(), does="true when the run exited with code 0"),
    activity=Field(Str()),
    worktree=Field(Str()),
    checkout=Field(Str()),
)

METRICS = Object("Metrics", empty=Field(Bool()), cells=Field(List(Str())), alerts=Field(List(Str())), run_dir=Field(Str()))

WORKER = Object(
    "Worker",
    found=Field(Bool(), does="false for a run groom never heard of; the answer is then 200 with the id alone"),
    id=Field(RUN_ID),
    run_id=Field(RUN_ID, required=False),
    state=Field(Enum(STATES), required=False),
    node=Field(Str(), required=False),
    gates=Field(List(GATE), required=False, does="one entry per gate, in path order"),
    running=Field(RUNNING, required=False, nullable=True, does="null once the run is finished or has no node"),
    strip=Field(STRIP, required=False, nullable=True, does="null once the run is finished or has no node"),
    ended=Field(Map(Str()), required=False, nullable=True),
    head=Field(HEAD, required=False),
    metrics=Field(METRICS, required=False),
    logs=Field(List(Str()), required=False),
    history=Field(List(Str()), required=False),
    figures_rev=Field(Int(), required=False),
    activity_rev=Field(Int(), required=False, does="rises on each span, log and transcript batch the run commits"),
    metrics_rev=Field(Int(), required=False, does="rises on each metric batch the run commits"),
)

ATTEND = Object(
    "AttendSettings",
    mode=Field(Enum(ATTEND_MODES), does="headless while an attendant answers gates, off otherwise"),
    last_mode=Field(Enum(ATTEND_MODES), does="the mode switched back on by the next enable"),
    cli=Field(Str(), opaque="the agent the environment's config names"),
    deny=Field(List(Str()), opaque="the environment's config names the denied tools"),
    sources=Field(Map(Str()), opaque="says whether each setting comes from the default or a config file, which the environment's history decides"),
)

ATTEND_INPUT = Object("AttendInput", enabled=Field(Bool(), required=False, does="true turns the attendant on; absent or false turns it off"))


ENTRY = Map(Str())
EMPTY_BECAUSE = "the book's groom has a fresh database and no telemetry, so no entry ever shows"

QUEUE_ERROR = Object(
    "QueueError",
    ok=Field(Bool()),
    error=Field(Str(), does="the reason, in the queue answers' own words"),
)

OUTBOX = Object(
    "Outbox",
    found=Field(Bool(), does="false when the run is unknown or waits on no gate"),
    file_path=Field(Str(), required=False, does="the first gate path in path order"),
    question=Field(Str(classes={"a short question": "Ship it?", "a question with a line break": "Ship it?\nYes or no."}), required=False, does="the question exactly as the run pushed it"),
    status=Field(Enum((GATE_STATUS,)), required=False),
)

ANSWER_INPUT = Object(
    "AnswerInput",
    file_path=Field(Str(classes={"an absolute path": "/work/gates/ask.md", "a relative path": "gates/ask.md"}), required=False, does="the gate file the answer is for"),
    answer=Field(Str(classes={"a short answer": "yes", "an answer with a line break": "yes\nship it"}), required=False, does="what the operator answers"),
)

MESSAGE_INPUT = Object(
    "MessageInput",
    body=Field(Str(classes={"a short message": "Please check the logs", "a message with a line break": "Please check\nthe logs"}), required=False, does="the operator's message; an empty body is refused"),
)

NOTICE = Object(
    "Notice",
    ok=Field(Bool()),
    message=Field(Str(), does="why groom did not do it"),
)

INBOX = Object("Inbox", messages=Field(List(Str()), does="the run's outstanding messages; none for a run that has no run directory"))

TREE = Object(
    "Tree",
    paths=Field(List(Str()), does="the repo-relative paths of the checkout"),
    failed=Field(Bool(), does="true when the read did not happen"),
    reported=Field(Bool(), does="true when the source says whether it failed"),
    served=Field(Enum(("sidecar", "volume")), does="which reader answered"),
    repos=Field(List(Str()), required=False, does="the checkouts a sidecar names, when it names them"),
)

FILE_TEXT = Object(
    "FileText",
    path=Field(Str(), does="the path asked for, as sent"),
    content=Field(Str()),
    lang=Field(Str(), does="the highlight.js language the file name implies, empty for a name with no grammar"),
    failed=Field(Bool()),
    reported=Field(Bool()),
    served=Field(Enum(("sidecar", "volume"))),
)

DIFF = Object(
    "Diff",
    diff=Field(Str()),
    untracked=Field(List(Str())),
    failed=Field(Bool()),
    reported=Field(Bool()),
    served=Field(Enum(("sidecar", "volume"))),
    repos=Field(List(Str()), required=False),
    based=Field(Bool(), required=False, does="whether a sidecar reported where the branch started, on a branch view"),
    base=Field(Str(), required=False),
    base_ref=Field(Str(), required=False),
    base_branch=Field(Str(), required=False),
    base_reason=Field(Str(), required=False),
)

REFRESHED = Object("Refreshed", ok=Field(Bool()), count=Field(Int(), does="how many workflows the scan found"))
RELOADED = Object("Reloaded", ok=Field(Bool()), reloaded=Field(Int(), does="how many sidecars were told"))
DONE = Object("Done", ok=Field(Bool(), does="false when nothing matched the id"))

COST = Object(
    "Cost",
    turns=Field(Int()),
    priced_turns=Field(Int()),
    reports_cost=Field(Bool()),
    usd=Field(Num(), nullable=True),
    est_usd=Field(Num(), nullable=True),
    output_tokens=Field(Int()),
    backends=Field(List(Str())),
)

TILES = Object(
    "Tiles",
    finished=Field(Bool()),
    reports_cost=Field(Bool()),
    cost_usd=Field(Num(), nullable=True),
    turns=Field(Int()),
    priced_turns=Field(Int()),
    active_s=Field(Num()),
    items_done=Field(Int(), nullable=True),
    items_total=Field(Int(), nullable=True),
    est_usd=Field(Num(), nullable=True),
    backends=Field(List(Str())),
    wall_s=Field(Num()),
    sessions=Field(Int()),
)

STANDING = Object(
    "Standing",
    gates=Field(Int()),
    gate_wait_s=Field(Num()),
    failed_steps=Field(Int()),
    retries=Field(Int()),
    failed_gate_checks=Field(Int()),
    churn_alerts=Field(Int()),
    problems=Field(Int()),
)

FACTS = Object("Facts", started_ts=Field(Num(), nullable=True), branch=Field(Str()), run_dir=Field(Str()))

OVERVIEW = Object(
    "Overview",
    run_id=Field(RUN_ID),
    finished=Field(Bool()),
    cost=Field(COST),
    figures=Field(TILES),
    standing=Field(STANDING),
    flows=Field(List(ENTRY), does=EMPTY_BECAUSE),
    nodes=Field(List(ENTRY), does=EMPTY_BECAUSE),
    compare=Field(Map(Str()), nullable=True),
    norm_runs=Field(Int()),
    items=Field(Map(Str()), nullable=True),
    time_s=Field(Num()),
    clock=Field(Map(Str()), nullable=True),
    models=Field(List(Str())),
    sessions=Field(List(ENTRY), does=EMPTY_BECAUSE),
    facts=Field(FACTS),
    as_of_ts=Field(Num(), nullable=True),
    ending=Field(Map(Str()), nullable=True, does="why a stopped run did not finish; null for a run with no recorded ending"),
)

HISTORY_TOTALS = Object(
    "HistoryTotals",
    runs=Field(Int()),
    reading=Field(Int()),
    unreadable=Field(Int()),
    spent_usd=Field(Num()),
    estimate_usd=Field(Num()),
    partly_priced=Field(Int()),
    active_s=Field(Num()),
    ready=Field(Int()),
    success=Field(Int()),
)

HISTORY = Object(
    "History",
    runs=Field(List(ENTRY, unordered="the summaries of the whole environment, which the book never made"), does="the runs that ended in the retention window, newest first"),
    totals=Field(HISTORY_TOTALS, opaque="adds up every ended run of the environment"),
    medians=Field(Map(Str()), opaque="the cost per item of every workflow the environment ran"),
    endings=Field(List(List(Str())), does="every ending a run may have, with the words the table shows"),
    unlisted=Field(Int(), opaque="counts the archives of the whole environment that have no summary yet"),
)

ACTIVITY = Object(
    "Activity",
    run_id=Field(RUN_ID),
    rows=Field(List(ENTRY), does=EMPTY_BECAUSE),
    items=Field(List(ENTRY), does=EMPTY_BECAUSE),
    problems=Field(Int()),
    log_count=Field(Int()),
    as_of=Field(Num(), opaque="the server's clock"),
)

RECORDS = Object(
    "Records",
    run_id=Field(RUN_ID),
    records=Field(List(ENTRY), does=EMPTY_BECAUSE),
    total=Field(Int()),
    metric_samples=Field(Int()),
    metrics=Field(Bool(), does="whether the metric samples were asked for"),
    next=Field(Str(), does="the cursor of the next page, empty on the last"),
)

MATCHES = Object(
    "Matches",
    run_id=Field(RUN_ID),
    query=Field(Str(), does="the text asked for, as sent"),
    matches=Field(List(ENTRY), does=EMPTY_BECAUSE),
)

ATTEND_QUEUE = Object(
    "AttendQueue",
    mode=Field(Enum(("off", "session", "headless")), does="the attendant's mode"),
    jobs=Field(List(ENTRY), does="every run waiting on an attendant, oldest first", opaque="the jobs of the whole environment"),
)

ATTEND_SESSIONS = Object(
    "AttendSessions",
    mode=Field(Enum(("off", "session", "headless"))),
    sessions=Field(List(ENTRY), does="the latest 200 attendances, newest first", opaque="the log of the whole environment"),
)

ATTEND_SESSION = Object(
    "AttendSession",
    session_id=Field(SESSION_ID, does="the session asked for, as sent"),
    present=Field(Bool(), does="whether a transcript of the session exists"),
    path=Field(Str(), opaque="where the environment keeps the transcript"),
    entries=Field(List(ENTRY), does="the conversation, one entry per message"),
    resume=Field(Str(), does="claude --resume followed by the session id", opaque="the session id in it is the name the run minted"),
    record=Field(Map(Str()), nullable=True, does="the ledger row of the session, null when the ledger has none"),
    attempts=Field(List(Str()), does="every session id the attendance tried"),
)

QUEUES = Object("Queues", queues=Field(List(ENTRY), does="every queue the home config names, with its concurrency and its occupancy"))
QUEUE_ITEMS = Object("QueueItems", items=Field(List(ENTRY), does="the queue's items, newest first, at most 200"))
ENQUEUE_INPUT = Object("EnqueueInput", params=Field(Map(Str()), required=False, does="the parameters of the item; anything but an object counts as none"))
ENQUEUED = Object("Enqueued", ok=Field(Bool()), item=Field(Map(Str()), does="the queued item as the ledger holds it"))
