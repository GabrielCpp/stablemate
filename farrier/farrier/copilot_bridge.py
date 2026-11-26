"""The script Copilot runs for each guard hook, and where it installs."""

from __future__ import annotations

from farrier.guard_bridge import render_bridge

COPILOT_GUARDS = ".copilot/hooks/farrier-guards.json"
COPILOT_BRIDGE = ".copilot/hooks/farrier-guards.py"
COPILOT_NAMES = {
    "bash": "Bash",
    "view": "Read",
    "create": "Write",
    "edit": "Edit",
    "str_replace_editor": "Edit",
    "apply_patch": "apply_patch",
    "grep": "Grep",
    "rg": "Grep",
    "glob": "Glob",
}
COPILOT_CLAUDE_INPUT = """
def claude_input(name, args):
    if isinstance(args, str):
        return {"command": args} if name in ("Bash", "apply_patch") else {}
    if name == "Bash":
        return {"command": args.get("command")}
    path = first(args, "path", "file_path", "filePath")
    if name == "Read":
        return {"file_path": path}
    if name in ("Grep", "Glob"):
        return {"pattern": args.get("pattern"), "path": args.get("path")}
    if name == "Write":
        return {"file_path": path, "content": first(args, "file_text", "content")}
    if name == "Edit":
        return {
            "file_path": path,
            "old_string": first(args, "old_str", "old_string", "oldString"),
            "new_string": first(args, "new_str", "new_string", "newString"),
        }
    if name == "apply_patch":
        text = first(args, "input", "patch", "patchText")
        if text is None:
            text = next((value for value in args.values() if isinstance(value, str)), None)
        return {"command": text}
    return dict(args)
"""
COPILOT_ARGS = """
    raw = event.get("toolName") or ""
    session = event.get("sessionId")
    args = event.get("toolArgs")
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            pass
    if not isinstance(args, (dict, str)):
        args = {}
"""
COPILOT_VERDICT = """
    verdict = decision.get("permissionDecision")
    if verdict in ("deny", "ask"):
        return {"permissionDecision": verdict, "permissionDecisionReason": decision.get("permissionDecisionReason") or DENIED}
    updated = decision.get("updatedInput")
    if name == "Bash" and isinstance(args, dict) and isinstance(updated, dict) and isinstance(updated.get("command"), str):
        return {"modifiedArgs": {**args, "command": updated["command"]}}
"""
COPILOT_BRIDGE_TEXT = render_bridge(
    COPILOT_NAMES,
    COPILOT_CLAUDE_INPUT,
    COPILOT_ARGS,
    '{"permissionDecision": "deny", "permissionDecisionReason": reason}',
    COPILOT_VERDICT,
    """
    session = event.get("sessionId")
    active = bool(event.get("stop_hook_active"))
""",
    """
    return {"decision": "block", "reason": reason}
""",
)
