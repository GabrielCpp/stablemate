"""The PreToolUse hook that holds a claude turn's subagents to the models its profile names.

The Agent tool lets the model pick any model alias for a subagent. The hook reads the
call on stdin and denies one whose `model` is outside the set given on its command line.
A call with no `model` inherits the turn's model and passes.
"""
from __future__ import annotations

import json
import re
import shlex
import sys
from collections.abc import Iterable, Sequence

HOOK_MODULE = "workhorse.runner.backends.model_guard"
AGENT_TOOL = "Agent"
FAMILY = re.compile(r"(?:^|[-/])(opus|sonnet|haiku|fable)(?:$|[-.\[])", re.IGNORECASE)


def family_alias(model: str) -> str | None:
    """The family alias of `model`: `opus` for `claude-opus-5-5`, and None when it names no family."""
    match = FAMILY.search(model)
    return match.group(1).lower() if match else None


def allowed_models(models: Iterable[str]) -> tuple[str, ...]:
    """Every model in `models` and each one's family alias, in order and without repeats."""
    allowed: dict[str, None] = {}
    for model in models:
        name = model.strip().lower()
        if not name:
            continue
        allowed[name] = None
        alias = family_alias(name)
        if alias:
            allowed[alias] = None
    return tuple(allowed)


def model_refusal(tool: str, tool_input: dict[str, object], allowed: Sequence[str]) -> str | None:
    """The reason to refuse an Agent call whose model is outside `allowed`, or None to let it run."""
    if tool != AGENT_TOOL:
        return None
    model = tool_input.get("model")
    if not isinstance(model, str) or not model.strip():
        return None
    if model.strip().lower() in allowed:
        return None
    return (
        f"Refused: the subagent model {model!r} is not one this run's profile names. "
        + f"Pass one of {', '.join(allowed)}, or leave `model` out to inherit this turn's model."
    )


def hook_command(models: Iterable[str]) -> str:
    """The command the CLI runs as the hook, allowing `models` and their family aliases."""
    return shlex.join([sys.executable, "-m", HOOK_MODULE, *allowed_models(models)])


def denial_output(reason: str) -> str:
    """The hook output that refuses the call."""
    output = {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}
    return json.dumps({"hookSpecificOutput": output})


def main(argv: Sequence[str] | None = None) -> int:
    """Read one tool call on stdin, and print a refusal when its model is not allowed."""
    allowed = list(sys.argv[1:] if argv is None else argv)
    try:
        data: object = json.loads(sys.stdin.read())
        if not isinstance(data, dict):
            raise ValueError("the call is not an object")
    except ValueError as error:
        print(denial_output(f"Refused: the model guard could not read the call: {error}"))
        return 0
    tool = data.get("tool_name")
    tool_input = data.get("tool_input")
    fields: dict[str, object] = {str(key): value for key, value in tool_input.items()} if isinstance(tool_input, dict) else {}
    reason = model_refusal(tool if isinstance(tool, str) else "", fields, allowed)
    if reason is not None:
        print(denial_output(reason))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
