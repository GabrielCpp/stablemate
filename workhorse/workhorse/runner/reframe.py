"""The prompts the recovery ladder sends instead of the node's own."""

from __future__ import annotations

from workhorse.runner.failure import OutputParseError
from workhorse.runner.spec import AgentNode


def retry_prompt(node: AgentNode, error: OutputParseError) -> str:
    """Corrective follow-up asking the agent to re-emit only the required outputs."""
    keys = [o.key for o in node.outputs]
    return (
        "Your previous response could not be parsed into this node's required "
        f"outputs.\nError: {error}\n\n"
        "Do not redo any work. Reply with ONLY a single JSON object "
        "(optionally inside a ```json fenced code block) containing exactly "
        f"these keys: {keys}. Include no other commentary before or after it."
    )


def timeout_retry_prompt(original_prompt: str, timeout: float) -> str:
    """Prepend a budget warning to a prompt whose previous attempt was killed for overrunning its wall-clock budget."""
    minutes = max(1, int(round(timeout / 60)))
    notice = (
        "⚠️ TIME BUDGET — your previous attempt at this task was STOPPED for "
        f"exceeding its wall-clock budget of ~{minutes} min ({int(timeout)}s), and "
        "all of its work was lost. You get the SAME ~"
        f"{minutes} min for this attempt. Do NOT run any command that cannot finish "
        "well within that budget: time long operations first, run measurements at a "
        "reduced scale if the full run will not fit, and leave margin to write your "
        "final result before time runs out. Then carry out the task below.\n\n"
    )
    return notice + original_prompt


def rephrase_prompt(original_prompt: str, node: AgentNode, attempt: int) -> str:
    """Reframe the node's prompt from scratch for a fresh-session retry."""
    output_keys = [o.key for o in node.outputs]
    strategies = [
        lambda p: (
            f"Please complete the following task carefully:\n\n{p}\n\n"
            f"IMPORTANT: reply with ONLY a JSON object containing these keys: "
            f"{output_keys}."
        ),
        lambda p: (
            f"Task: {p[:1000]}\n\n"
            "Reply with ONLY this JSON object, filling in the values:\n"
            "```json\n{\n"
            + "\n".join(f'  "{key}": <value>,' for key in output_keys)
            + "\n}\n```"
        ),
        lambda p: (
            "Complete this task as best you can; if unsure, provide reasonable "
            f"values.\n\nTask summary: {p[:500]}\n\n"
            f"You MUST reply with ONLY a JSON object with keys: {output_keys}."
        ),
    ]
    idx = min(attempt - 1, len(strategies) - 1)
    return strategies[idx](original_prompt)
