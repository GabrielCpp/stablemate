"""The script Antigravity runs for each guard hook, and where it installs."""

from __future__ import annotations

from farrier.guard_bridge import render_bridge

ANTIGRAVITY_GUARDS = ".gemini/config/hooks.json"
ANTIGRAVITY_BRIDGE = ".gemini/config/hooks/farrier-guards.py"
ANTIGRAVITY_TOOLS = {
    "shell": "run_command",
    "edit": "write_to_file|replace_file_content|multi_replace_file_content",
    "read": "view_file",
    "search": "grep_search",
}
ANTIGRAVITY_NAMES = {
    "run_command": "Bash",
    "view_file": "Read",
    "write_to_file": "Write",
    "replace_file_content": "Edit",
    "multi_replace_file_content": "Edit",
    "grep_search": "Grep",
    "find_by_name": "Glob",
}
ANTIGRAVITY_CLAUDE_INPUT = """
def claude_input(name, args):
    if name == "Bash":
        return {"command": first(args, "command", "commandLine")}
    path = first(args, "path", "filePath", "absolutePath", "targetFile")
    if name == "Read":
        return {"file_path": path}
    if name in ("Grep", "Glob"):
        return {"pattern": first(args, "pattern", "query"), "path": first(args, "path", "searchPath")}
    if name == "Write":
        return {"file_path": path, "content": first(args, "content", "codeContent")}
    if name == "Edit":
        return {
            "file_path": path,
            "old_string": first(args, "oldString", "targetContent"),
            "new_string": first(args, "newString", "replacementContent"),
        }
    return dict(args)
"""
ANTIGRAVITY_ARGS = """
    args = event.get("toolInput")
    if not isinstance(args, dict):
        args = {}
"""
ANTIGRAVITY_VERDICT = """
    if decision.get("permissionDecision") == "deny":
        return {"decision": "deny", "reason": decision.get("permissionDecisionReason") or DENIED}
    if decision.get("decision") == "deny":
        return {"decision": "deny", "reason": decision.get("reason") or DENIED}
"""
ANTIGRAVITY_BRIDGE_TEXT = render_bridge(
    ANTIGRAVITY_NAMES,
    ANTIGRAVITY_CLAUDE_INPUT,
    ANTIGRAVITY_ARGS,
    '{"decision": "deny", "reason": done.stderr.strip() or DENIED}',
    ANTIGRAVITY_VERDICT,
    "stopHookActive",
)
