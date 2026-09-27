"""Tests for the hook that holds a confined codex turn to its profile (``runner/backends/codex_guard.py``)."""

from __future__ import annotations

import io
import json
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from workhorse.runner.backends.codex_guard import Policy, ToolCall, decide, main, patch_denial, shell_denial

BOOK = Path("/work/app/docs/book")
SOURCE = Path("/runs/r1/source")
SKILLS = Path("/work/app/.claude/skills")
CHECK = "/venv/bin/python -m check /runs/r1/state.json"
POLICY = Policy(cwd=BOOK, read_roots=(BOOK, SOURCE, SKILLS), commands=("ostler", CHECK))


def _allowed(command: str) -> bool:
    return shell_denial(command, POLICY) is None


def test_the_profile_commands_run_with_their_own_arguments():
    assert _allowed(CHECK)
    assert _allowed(f"{CHECK} 2>&1 | tail -n 40")
    assert _allowed("ostler check-page overview.md")


def test_read_only_commands_run_on_the_turn_s_own_paths():
    assert _allowed("cat overview.md")
    assert _allowed(f"sed -n '1,120p' {SOURCE}/cli.py")
    assert _allowed(f"rg -n 'def main' {SOURCE}")
    assert _allowed(f"cat {SKILLS}/acme/SKILL.md")
    assert _allowed("ls")


def test_a_timeout_bounds_a_command_without_changing_what_it_may_do():
    assert _allowed("timeout 60 cat overview.md")
    assert _allowed(f"timeout 5m {CHECK}")
    assert not _allowed("timeout 60 rm overview.md")
    assert not _allowed("timeout 60 cat /etc/passwd")
    assert not _allowed("timeout --signal=KILL 60 cat overview.md")


def test_a_path_outside_the_turn_s_roots_is_refused():
    assert not _allowed("cat /etc/passwd")
    assert not _allowed("cat ../../secrets.env")
    assert not _allowed("cat ~/.ssh/id_rsa")
    assert not _allowed(f"cat {BOOK}/../../../etc/passwd")
    assert not _allowed("ostler check-page /etc/passwd")


def test_a_path_hidden_in_an_option_value_is_refused():
    assert not _allowed("rg --files --glob=/etc/passwd .")
    assert not _allowed("ls --directory=/etc")


def test_a_search_pattern_is_not_read_as_a_path_but_a_pattern_file_is():
    assert _allowed("rg -n '/usr/local' .")
    assert _allowed("grep -e /etc .")
    assert not _allowed("grep -f /etc/passwd .")
    assert not _allowed("grep --regexp=x /etc/passwd")
    assert not _allowed("grep -e x /etc/passwd")


def test_a_command_that_writes_or_runs_more_is_refused():
    assert not _allowed("rm overview.md")
    assert not _allowed("python -c 'print(1)'")
    assert not _allowed("cat a.md > b.md")
    assert not _allowed("cat a.md; rm b.md")
    assert not _allowed("cat a.md && rm b.md")
    assert not _allowed("cat $(which python)")
    assert not _allowed("cat `ls`")
    assert not _allowed("cat a.md\nrm b.md")
    assert not _allowed("find . -delete")
    assert not _allowed("find . -exec rm {} +")
    assert not _allowed("rg --pre cat x .")


def test_sed_only_prints_lines():
    assert not _allowed("sed -i 's/a/b/' overview.md")
    assert not _allowed("sed -n 'w /tmp/x' overview.md")
    assert _allowed("sed -n '10,40p;90,$p' overview.md")


def test_a_profile_command_spelled_differently_is_not_that_command():
    assert not _allowed("/venv/bin/python -m check /runs/r1/other.json")


def test_a_patch_writes_only_under_the_cwd():
    inside = "*** Begin Patch\n*** Update File: concepts/ledger.md\n@@\n-a\n+b\n*** End Patch"
    absolute = f"*** Begin Patch\n*** Add File: {BOOK}/new.md\n+x\n*** End Patch"
    climbing = "*** Begin Patch\n*** Add File: ../../app.py\n+x\n*** End Patch"
    moved = "*** Begin Patch\n*** Update File: a.md\n*** Move to: /etc/a.md\n*** End Patch"
    assert patch_denial(inside, POLICY) is None
    assert patch_denial(absolute, POLICY) is None
    assert patch_denial(climbing, POLICY) is not None
    assert patch_denial(moved, POLICY) is not None


def _call(payload: object) -> ToolCall:
    return ToolCall.from_json(json.dumps(payload))


def test_decide_checks_only_shell_calls_and_patches():
    assert decide(_call({"tool_name": "update_plan", "tool_input": {"plan": []}}), POLICY) is None
    assert decide(_call({"tool_name": "Bash", "tool_input": {"command": "cat overview.md"}}), POLICY) is None
    refusal = decide(_call({"tool_name": "Bash", "tool_input": {"command": "rm overview.md"}}), POLICY)
    assert refusal is not None and refusal.startswith("Refused: `rm`")
    assert decide(_call({"tool_name": "Bash", "tool_input": {}}), POLICY) is not None
    assert decide(_call({"tool_name": "Bash", "tool_input": {"command": ["rm", "x"]}}), POLICY) is not None


def _hook_output(argv: list[str], payload: str) -> str:
    out = io.StringIO()
    with patch("sys.stdin", io.StringIO(payload)), redirect_stdout(out):
        assert main(argv) == 0
    return out.getvalue()


def test_the_hook_prints_a_refusal_only_for_a_forbidden_call():
    with tempfile.TemporaryDirectory() as tmp:
        policy_path = Path(tmp) / "policy.json"
        _ = policy_path.write_text(POLICY.to_json(), encoding="utf-8")
        allowed = _hook_output([str(policy_path)], json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}))
        refused = _hook_output([str(policy_path)], json.dumps({"tool_name": "Bash", "tool_input": {"command": "rm x"}}))
    assert allowed == ""
    assert json.loads(refused)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_the_hook_refuses_when_it_cannot_read_its_policy():
    refused = _hook_output(["/nonexistent/policy.json"], json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}))
    assert json.loads(refused)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_the_hook_refuses_a_call_that_is_not_an_object():
    with tempfile.TemporaryDirectory() as tmp:
        policy_path = Path(tmp) / "policy.json"
        _ = policy_path.write_text(POLICY.to_json(), encoding="utf-8")
        refused = _hook_output([str(policy_path)], json.dumps(["Bash", "rm x"]))
    assert json.loads(refused)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_the_policy_survives_its_round_trip():
    assert Policy.from_json(POLICY.to_json()) == POLICY


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
