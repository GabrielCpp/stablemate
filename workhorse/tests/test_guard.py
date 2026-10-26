"""Tests for the hook that holds a confined codex or claude turn to its profile (``runner/backends/guard.py``)."""

from __future__ import annotations

import io
import json
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pytest

from workhorse.runner.backends.guard import Policy, ToolCall, call_refusal, main, patch_denial, policy_file
from workhorse.runner.backends.guard_shell import shell_denial

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


ALLOWED_COMMANDS = (
    "sort file.txt",
    "grep -rl foo . | sort | uniq -c",
    "sort -u a.txt",
    "sort --unique a.txt",
    "uniq a.txt",
    "uniq -f 1 a.txt",
    "true",
    "ls || true",
    "ls; pwd",
    "ls;",
    "cd sub && ls",
    f"cd {BOOK} ; cat x",
    "find . -name '*.md' | xargs grep -l foo",
    "find . -print0 | xargs -0 -n1 wc -l",
    "ls | xargs -I{} cat {}",
    f"ls && {CHECK}",
    "ls && ostler check-page overview.md",
)


@pytest.mark.parametrize("command", ALLOWED_COMMANDS)
def test_a_widened_shell_call_is_allowed(command: str):
    assert shell_denial(command, POLICY) is None


REFUSED_COMMANDS = (
    ("sort -o out.txt a.txt", "`sort -o`"),
    ("sort -uo out a", "`sort -o`"),
    ("sort --output=out a", "`sort --output`"),
    ("sort --compress-program=sh a", "`sort --compress-program`"),
    ("sort --out=x a", "`sort --out`"),
    ("sort --o x a", "`sort --o`"),
    ("sort --compress=sh a", "`sort --compress`"),
    ("sort --co=sh a", "`sort --co`"),
    ("uniq a.txt out.txt", "`uniq`"),
    ("ls | xargs rm", "`rm`"),
    ("ls | xargs", "`xargs`"),
    ("ls | xargs -a list cat", "`xargs -a`"),
    ("ls | xargs sh -c 'x'", "`sh`"),
    ("ls | xargs xargs rm", "`rm`"),
    ("cd", "`cd`"),
    ("cd -", "`cd`"),
    ("cd ~", "`~`"),
    ("cd ..", "`..`"),
    ("cd /etc", "`/etc`"),
    ("ls | cd sub", "`cd`"),
    ("cd a b", "`cd`"),
    ("; ls", "empty"),
    ("ls ;; pwd", "`;;`"),
    ("ls && && pwd", "empty"),
    ("ls &&", "empty"),
    ("ls & pwd", "`&`"),
    ("ls > out", "`>`"),
    ("(ls)", "`(`"),
    ("ls |& cat", "`|&`"),
    ("ls; rm x", "`rm`"),
    ("true; cat /etc/passwd", "`/etc/passwd`"),
)


@pytest.mark.parametrize(("command", "cause"), REFUSED_COMMANDS)
def test_a_widened_shell_call_is_refused_for_its_cause(command: str, cause: str):
    denial = shell_denial(command, POLICY)
    assert denial is not None
    assert cause in denial


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


def test_the_call_refusal_lets_a_tool_it_does_not_judge_through():
    assert call_refusal(_call({"tool_name": "update_plan", "tool_input": {"plan": []}}), POLICY) is None
    assert call_refusal(_call({"tool_name": "Bash", "tool_input": {"command": "cat overview.md"}}), POLICY) is None
    refusal = call_refusal(_call({"tool_name": "Bash", "tool_input": {"command": "rm overview.md"}}), POLICY)
    assert refusal is not None and refusal.startswith("Refused: `rm`")
    assert call_refusal(_call({"tool_name": "Bash", "tool_input": {}}), POLICY) is not None
    assert call_refusal(_call({"tool_name": "Bash", "tool_input": {"command": ["rm", "x"]}}), POLICY) is not None


HOME_SKILLS = Path("/home/op/.claude")
CLAUDE_POLICY = Policy(cwd=BOOK, read_roots=(BOOK, SOURCE, HOME_SKILLS), commands=())


def _claude_refusal(tool: str, **tool_input: object) -> str | None:
    return call_refusal(_call({"tool_name": tool, "tool_input": tool_input}), CLAUDE_POLICY)


def test_a_claude_write_lands_only_under_the_cwd():
    assert _claude_refusal("Write", file_path=f"{BOOK}/new.md", content="x") is None
    assert _claude_refusal("Edit", file_path=f"{BOOK}/concepts/a.md") is None
    assert _claude_refusal("MultiEdit", file_path="concepts/a.md") is None
    assert _claude_refusal("Write", file_path="/work/app/src/app.py", content="x") is not None
    assert _claude_refusal("Edit", file_path=f"{BOOK}/../../app.py") is not None
    assert _claude_refusal("Write", file_path=f"{HOME_SKILLS}/skills/x/SKILL.md") is not None
    assert _claude_refusal("Write", content="x") is not None
    assert _claude_refusal("Write", file_path=7) is not None


def test_a_claude_notebook_edit_is_judged_by_its_notebook_path():
    assert _claude_refusal("NotebookEdit", notebook_path=f"{BOOK}/a.ipynb") is None
    assert _claude_refusal("NotebookEdit", notebook_path="/work/app/a.ipynb") is not None
    assert _claude_refusal("NotebookEdit") is not None


def test_a_claude_read_stays_under_the_read_roots():
    assert _claude_refusal("Read", file_path=f"{HOME_SKILLS}/skills/x/SKILL.md") is None
    assert _claude_refusal("Read", file_path=f"{SOURCE}/cli.py") is None
    assert _claude_refusal("Read", file_path="/etc/passwd") is not None
    assert _claude_refusal("Read", file_path=f"{HOME_SKILLS}/../.ssh/id_rsa") is not None
    assert _claude_refusal("Read") is not None


def test_a_claude_search_without_a_path_runs_in_the_cwd():
    assert _claude_refusal("Grep", pattern="needle") is None
    assert _claude_refusal("Glob", pattern="*.md") is None
    assert _claude_refusal("Grep", pattern="needle", path=str(SOURCE)) is None
    assert _claude_refusal("Grep", pattern="needle", path="/etc") is not None
    assert _claude_refusal("Glob", pattern="*", path="/work/app") is not None


def test_a_claude_shell_call_passes_the_same_judge_as_a_codex_one():
    assert _claude_refusal("Bash", command=f"cat {SOURCE}/cli.py") is None
    assert _claude_refusal("Bash", command="rm -rf /") is not None


def test_the_policy_file_holds_the_policy_until_the_turn_ends():
    with policy_file(CLAUDE_POLICY) as path:
        assert Policy.from_json(path.read_text(encoding="utf-8")) == CLAUDE_POLICY
    assert not path.exists()


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


def test_the_hook_refuses_when_its_policy_is_not_the_strings_it_writes():
    malformed = (
        ["not", "an", "object"],
        {"cwd": "/work", "read_roots": ["/work"], "commands": "make test"},
        {"cwd": "/work", "read_roots": [7], "commands": []},
        {"read_roots": [], "commands": []},
    )
    with tempfile.TemporaryDirectory() as tmp:
        policy_path = Path(tmp) / "policy.json"
        for policy in malformed:
            _ = policy_path.write_text(json.dumps(policy), encoding="utf-8")
            refused = _hook_output([str(policy_path)], json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}))
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
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
