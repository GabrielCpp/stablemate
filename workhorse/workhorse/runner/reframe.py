"""The prompts the recovery ladder sends instead of the node's own."""

from __future__ import annotations

from workhorse.runner.failure import OutputParseError
from workhorse.runner.spec import AgentNode


def retry_prompt(node: AgentNode, error: OutputParseError) -> str:
    """Corrective follow-up asking the agent to re-emit only the required outputs."""
    keys = [o.key for o in node.outputs]
    if any(o.verbatim for o in node.outputs):
        return (
            "Your previous response was empty.\n\n"
            "Do not redo any work. Reply again with the whole answer the task asked for."
        )
    return (
        "Your previous response could not be parsed into this node's required "
        f"outputs.\nError: {error}\n\n"
        "Do not redo any work. Reply with ONLY a single JSON object "
        "(optionally inside a ```json fenced code block) containing exactly "
        f"these keys: {keys}. Include no other commentary before or after it."
    )


def timeout_retry_prompt(original_prompt: str, timeout: float) -> str:
    """Prepend a silence warning to a prompt whose previous attempt was cut for going quiet."""
    minutes = max(1, int(round(timeout / 60)))
    notice = (
        "⚠️ NO PROGRESS REPORTED — your previous attempt at this task was STOPPED "
        f"after ~{minutes} min ({int(timeout)}s) without producing a single line of "
        "output, and all of its work was lost. There is no limit on how long the "
        "work may take, only on how long you may go silent. Keep reporting: run one "
        "bounded command at a time rather than a single command that blocks for "
        "minutes, and if a command hangs with no output, stop it and try another "
        "way. Then carry out the task below.\n\n"
    )
    return notice + original_prompt


def rephrase_prompt(original_prompt: str, node: AgentNode, attempt: int) -> str:
    """Reframe the node's prompt from scratch for a fresh-session retry.

    Each attempt states the reply more plainly, and each carries the whole task, since an answer
    to part of a task is not the node's answer. A node whose answer is its reply text is never
    asked for JSON.
    """
    if any(o.verbatim for o in node.outputs):
        return (
            f"Please complete the following task carefully:\n\n{original_prompt}\n\n"
            "IMPORTANT: reply with the whole answer the task asked for, in the form it asked for."
        )
    output_keys = [o.key for o in node.outputs]
    strategies = [
        lambda p: (
            f"Please complete the following task carefully:\n\n{p}\n\n"
            f"IMPORTANT: reply with ONLY a JSON object containing these keys: "
            f"{output_keys}."
        ),
        lambda p: (
            f"Task: {p}\n\n"
            "Reply with ONLY this JSON object, filling in the values:\n"
            "```json\n{\n"
            + "\n".join(f'  "{key}": <value>,' for key in output_keys)
            + "\n}\n```"
        ),
        lambda p: (
            "Complete this task as best you can; if unsure, provide reasonable "
            f"values.\n\nTask: {p}\n\n"
            f"You MUST reply with ONLY a JSON object with keys: {output_keys}."
        ),
    ]
    idx = min(attempt - 1, len(strategies) - 1)
    return strategies[idx](original_prompt)
