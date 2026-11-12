"""The bodies groom sends and accepts, each declared once."""

from ostler.book import Bool, Enum, Field, Id, Int, List, Map, Num, Object, Str

from ...model.records import ATTEND_MODES, GATE_STATUS, LIVE, STATES, Run

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

ACK = Object("Ack", ok=Field(Bool(), does="true when groom took the push, false when it lacked what it needs to know the run"))

OPAQUE_CLOCK = "the dashboard fills it from run telemetry, which a push never carries"

PROGRESS = Object(
    "Progress",
    container_id=Field(RUN_ID, required=False, does="the run's container id; only its first 12 characters count"),
    name=Field(RUN_ID, required=False, does="the run's display name; a new run without one shows its container id"),
    repo_name=Field(Str(), required=False),
    repo_branch=Field(Str(), required=False),
    current_node=Field(Str(), required=False, does="the node the run is in"),
)

BLOCKED = Object(
    "Blocked",
    container_id=Field(RUN_ID, required=False),
    file_path=Field(Str(), required=False, does="the gate file the run waits on; one gate per path"),
    question=Field(Str(), required=False, does="what the run asks the operator"),
    name=Field(RUN_ID, required=False),
    repo_name=Field(Str(), required=False),
    repo_branch=Field(Str(), required=False),
)

EXITED = Object(
    "Exited",
    container_id=Field(RUN_ID, required=False),
    exit_code=Field(Int(), required=False, does="the process exit code"),
    name=Field(RUN_ID, required=False),
    repo_name=Field(Str(), required=False),
    repo_branch=Field(Str(), required=False),
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

FLEET = Object(
    "Fleet",
    type=Field(Str()),
    ts=Field(Num(), opaque="the server's clock"),
    scanning=Field(Bool(), opaque="a discovery scan may be running"),
    runs=Field(List(ROW), does="every run the filter matches, blocked first, then running, then finished, each by name"),
    attention=Field(List(ALERT), does="a blocked event per gate and an ended event per finished run; never filtered by the query"),
    status=Field(STATUS, opaque="counts every run of the environment"),
    store=Field(STORE_HEALTH, opaque="the state of the environment's database"),
    attend=Field(ATTEND_SUMMARY),
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
