"""A command-line flow stops at the command whose outcome is wrong: each step's checks and read-backs run inside that step's `qa.at_node`, and the walk never reaches the next command."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from ostler.qa.compile import Plan, Refusal, compile_plan_gaps
from ostler.qa.context import build_context

from conftest import write

HARNESS_DIR = Path(__file__).resolve().parents[1] / "ostler" / "qa" / "harness"
CLI = "docs/services/tally/tally.md"
FLOW = "docs/services/tally/flows/pay-a-bill.md"
PAY = f"{CLI}#pay"
ADD = f"{CLI}#add"
SHOW = f"{CLI}#show"
PAY_MOVE = f"okf:{PAY}:moves:1"

TOOL = """#!{python}
import json
import pathlib
import sys

MODE = {mode!r}
pathlib.Path({log!r}).open("a").write(sys.argv[1] + "\\n")
bill = pathlib.Path("bill.json")
command = sys.argv[1]
if command == "add":
    bill.write_text(json.dumps({{"status": "issued"}}))
    print(bill.read_text())
elif command == "pay":
    if not bill.exists():
        print("no bill to pay", file=sys.stderr)
        sys.exit(2)
    if MODE == "good":
        bill.write_text(json.dumps({{"status": "paid"}}))
        print(bill.read_text())
    elif MODE == "wrong-output":
        bill.write_text(json.dumps({{"status": "paid"}}))
        print(json.dumps({{"status": "issued"}}))
    else:
        print(json.dumps({{"status": "paid"}}))
elif command == "show":
    print(bill.read_text())
"""

STATES = """
## Data states

### issued
- of: bill
- observe: [show](#show)
- verify: json_path(path="$.status", equals="issued")
{issued_fixture}
### paid
- of: bill
- observe: [show](#show)
- verify: json_path(path="$.status", equals="paid")
"""

REFUSAL = """
## Invocations

### pay-without-a-bill
- on: [pay](#pay)
- trigger: the caller pays before any bill exists.
- does:
  - Refuses to pay a bill that is not on file.
- run: invoke(argv=["pay"])
{verifies}"""

PASSAGE = """
## Passages

### Add and pay

- steps:
  - [add](#add)
  - [pay](#pay)
"""


def _cli(*, pay_verify: str = "exit_status(code=0)", pay_moves: bool = False, extra: str = "",
         issued_fixture: str = "- fixture: none, because a bill is already on file\n") -> str:
    moves = "- moves: [Bill issued](#issued) to [Bill paid](#paid)\n" if pay_moves else ""
    add_moves = "- moves: to [Bill issued](#issued)\n" if pay_moves else ""
    states = STATES.format(issued_fixture=issued_fixture) if pay_moves else ""
    return f"""---
type: cli
title: Tally
---
# Tally

- binary: tally

## Commands

### add
{add_moves}- run: invoke(argv=["add"])
- verify: exit_status(code=0)

### pay
{moves}- run: invoke(argv=["pay"])
- verify: {pay_verify}

### show
- run: invoke(argv=["show"])
- verify: exit_status(code=0)
{extra}{states}"""


def _flow(*steps: tuple[str, str]) -> str:
    listed = "\n".join(f"  - [{label}](../tally.md#{anchor})" for label, anchor in steps)
    return f"""---
type: flow
title: Pay a bill
---
# Pay a bill

- start: [Tally](../tally.md)
- steps:
{listed}
- end: [Tally](../tally.md)
- fixture: none, because nothing is arranged
- verify: exit_status(code=0)
"""


ADD_PAY_SHOW = _flow(("add", "add"), ("pay", "pay"), ("show", "show"))


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _compile(root: Path, cli: str, flow: str | None = ADD_PAY_SHOW) -> Plan | Refusal:
    write(root / CLI, cli)
    if flow is not None:
        write(root / FLOW, flow)
    _git(root, "init")
    _git(root, "config", "user.email", "qa@example.com")
    _git(root, "config", "user.name", "QA")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "base")
    return compile_plan_gaps(build_context(root, base="HEAD", whole_book=True), story="demo")


def _plan(root: Path, cli: str, flow: str | None = ADD_PAY_SHOW) -> Plan:
    planned = _compile(root, cli, flow)
    assert isinstance(planned, Plan)
    return planned


def _scenario(planned: Plan, needle: str) -> str:
    [name] = [line.split("(")[0].removeprefix("def ") for line in planned.source.splitlines()
              if line.startswith("def ") and needle in line]
    return name


def _body(planned: Plan, needle: str) -> str:
    source = planned.source
    start = source.index(f"def {_scenario(planned, needle)}")
    end = source.find("\n@scenario", start)
    return source[start:] if end == -1 else source[start:end]


def _walk(root: Path, planned: Plan, name: str, mode: str) -> tuple[int, list[dict], list[str]]:
    bin_dir = root / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = root / "calls.log"
    tool = bin_dir / "tally"
    tool.write_text(TOOL.format(python=sys.executable, mode=mode, log=str(log)), encoding="utf-8")
    tool.chmod(0o755)
    module = root / "qa_plan.py"
    module.write_text(planned.source, encoding="utf-8")
    sink_path = root / "records.jsonl"
    context = json.dumps({"root": str(root), "spec_dir": str(root), "qa_dir": str(root / "qa"),
                          "book_fixtures": {}, "lap_dir": "", "tools": {"tally": "tally"}})
    command = [sys.executable, "-m", "ostler_qa", "run", str(module), name.replace("_", "-"), context]
    with sink_path.open("w") as sink:
        done = subprocess.run(  # noqa: S603
            command, capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False, pass_fds=(sink.fileno(),),
            env={"PYTHONPATH": str(HARNESS_DIR), "PATH": f"{bin_dir}:/usr/bin:/bin",
                 "OSTLER_QA_RECORD_FD": str(sink.fileno())},
        )
    records = [json.loads(line) for line in sink_path.read_text(encoding="utf-8").splitlines() if line]
    calls = log.read_text(encoding="utf-8").split() if log.exists() else []
    return done.returncode, records, calls


def _failed(records: list[dict]) -> list[dict]:
    return [r for r in records if r["type"] == "assert" and not r["passed"]]


PAY_PAID = 'json_path(path="$.status", equals="paid")'


def test_a_wrong_output_on_the_middle_command_fails_at_that_command_and_the_third_never_runs(tmp_path: Path) -> None:
    planned = _plan(tmp_path, _cli(pay_verify=PAY_PAID))
    name = _scenario(planned, "pay_a_bill")
    body = _body(planned, "pay_a_bill")
    assert body.count("with qa.at_node(") == 3
    assert f'with qa.at_node("{PAY}")' in body
    code, records, calls = _walk(tmp_path, planned, name, "wrong-output")
    assert code != 0, records
    [failure] = _failed(records)
    assert failure["node"] == PAY
    assert calls == ["add", "pay"]


def test_the_same_flow_passes_against_a_tool_that_prints_the_right_output(tmp_path: Path) -> None:
    planned = _plan(tmp_path, _cli(pay_verify=PAY_PAID))
    code, records, calls = _walk(tmp_path, planned, _scenario(planned, "pay_a_bill"), "good")
    assert code == 0, records
    assert calls == ["add", "pay", "show"]


def test_a_refusal_step_does_not_stop_the_walk(tmp_path: Path) -> None:
    refusal = REFUSAL.format(verifies="- verify: exit_status(code=2)\n")
    flow = _flow(("pay-without-a-bill", "pay-without-a-bill"), ("add", "add"), ("pay", "pay"))
    planned = _plan(tmp_path, _cli(extra=refusal), flow)
    body = _body(planned, "pay_a_bill")
    assert f'with qa.at_node("{CLI}#pay-without-a-bill")' in body
    code, records, calls = _walk(tmp_path, planned, _scenario(planned, "pay_a_bill"), "good")
    assert code == 0, records
    assert calls == ["pay", "add", "pay"]


def test_a_step_that_links_a_node_with_two_outcomes_is_an_uncompilable_claim(tmp_path: Path) -> None:
    refusal = REFUSAL.format(verifies="- verify: exit_status(code=2)\n- verify: exit_status(code=3)\n")
    flow = _flow(("pay-without-a-bill", "pay-without-a-bill"), ("add", "add"))
    planned = _compile(tmp_path, _cli(extra=refusal), flow)
    gaps = [gap for gap in planned.gaps if gap.kind == "uncompilable-claim" and "several outcomes" in gap.detail]
    assert gaps
    assert "link one case per step" in gaps[0].detail
    assert not isinstance(planned, Plan) or "pay_a_bill" not in planned.source


def test_a_passage_step_runs_each_command_it_holds_in_its_own_block(tmp_path: Path) -> None:
    flow = _flow(("Add and pay", "add-and-pay"), ("show", "show"))
    planned = _plan(tmp_path, _cli(extra=PASSAGE), flow)
    body = _body(planned, "pay_a_bill")
    assert body.count(".run(") == 3
    for node in (ADD, PAY, SHOW):
        assert f'with qa.at_node("{node}")' in body
    assert body.index(f'at_node("{ADD}")') < body.index(f'at_node("{PAY}")') < body.index(f'at_node("{SHOW}")')
    code, records, calls = _walk(tmp_path, planned, _scenario(planned, "pay_a_bill"), "good")
    assert code == 0, records
    assert calls == ["add", "pay", "show"]


def test_a_move_read_back_fails_at_the_command_that_left_the_record_in_the_old_state(tmp_path: Path) -> None:
    planned = _plan(tmp_path, _cli(pay_moves=True))
    body = _body(planned, "pay_a_bill")
    assert 'qa.holds("paid"' in body
    code, records, calls = _walk(tmp_path, planned, _scenario(planned, "pay_a_bill"), "keeps")
    assert code != 0, records
    [failure] = _failed(records)
    assert failure["node"] == PAY
    assert failure["holds"] == "issued"
    assert calls == ["add", "show", "pay", "show"]


def test_a_move_read_back_passes_when_the_command_leaves_the_record_in_the_new_state(tmp_path: Path) -> None:
    planned = _plan(tmp_path, _cli(pay_moves=True))
    code, records, calls = _walk(tmp_path, planned, _scenario(planned, "pay_a_bill"), "good")
    assert code == 0, records
    assert calls == ["add", "show", "pay", "show", "show"]


@pytest.fixture
def shipped_bill(tmp_path: Path) -> Path:
    write(tmp_path / "bill.json", '{"status": "issued"}\n')
    return tmp_path


def test_a_cli_move_no_flow_takes_gets_a_one_move_walk_on_the_cli_target(shipped_bill: Path) -> None:
    planned = _plan(shipped_bill, _cli(pay_moves=True), None)
    assert not [gap for gap in planned.gaps if gap.obligation_id == PAY_MOVE]
    name = _scenario(planned, "pay_moves_1")
    body = _body(planned, "pay_moves_1")
    assert 'with qa.at_node("' + f"{CLI}#issued" + '")' in body
    assert body.index("before_move") < body.index("moved_1")
    assert "qa.http" not in planned.source
    assert 'driver="python"' in planned.source or "driver='python'" in planned.source
    code, records, calls = _walk(shipped_bill, planned, name, "good")
    assert code == 0, records
    assert calls == ["show", "pay", "show"]
