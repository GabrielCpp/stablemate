"""The script Antigravity runs for each guard hook, and where it installs."""

from __future__ import annotations

from farrier.guard_bridge import render_bridge

ANTIGRAVITY_GUARDS = ".gemini/config/hooks.json"
ANTIGRAVITY_BRIDGE = ".gemini/config/hooks/farrier-guards.py"
ANTIGRAVITY_HOOK = "farrier-guards"
ANTIGRAVITY_TOOLS = {
    "shell": "run_command",
    "edit": "edit_file|write_file|write_to_file|replace_file_content|multi_replace_file_content",
    "read": "read_file|view_file",
    "search": "grep_search|find_by_name",
}
ANTIGRAVITY_NAMES = {
    "run_command": "Bash",
    "view_file": "Read",
    "read_file": "Read",
    "write_file": "Write",
    "edit_file": "Edit",
    "write_to_file": "Write",
    "replace_file_content": "Edit",
    "multi_replace_file_content": "Edit",
    "grep_search": "Grep",
    "find_by_name": "Glob",
}
ANTIGRAVITY_CLAUDE_INPUT = """
def pick(args, *keys):
    folded = {str(key).lower(): value for key, value in args.items()}
    return next((folded[key.lower()] for key in keys if key.lower() in folded), None)


def chunks(args):
    found = pick(args, "ReplacementChunks", "Chunks")
    if isinstance(found, list) and found and isinstance(found[0], dict):
        return found[0]
    return args


def claude_input(name, args):
    if name == "Bash":
        return {"command": pick(args, "CommandLine", "Command")}
    path = pick(args, "AbsolutePath", "TargetFile", "Path", "FilePath", "File")
    if name == "Read":
        return {"file_path": path}
    if name in ("Grep", "Glob"):
        return {
            "pattern": pick(args, "Query", "Pattern"),
            "path": pick(args, "SearchPath", "SearchDirectory", "Path", "Directory"),
        }
    if name == "Write":
        return {"file_path": path, "content": pick(args, "CodeContent", "Content")}
    if name == "Edit":
        chunk = chunks(args)
        return {
            "file_path": path,
            "old_string": pick(chunk, "Target", "TargetContent", "OldString"),
            "new_string": pick(chunk, "Replacement", "ReplacementContent", "NewString"),
        }
    return dict(args)
"""
ANTIGRAVITY_ARGS = """
    call = event.get("toolCall")
    if not isinstance(call, dict):
        call = {}
    raw = call.get("name") or ""
    session = event.get("conversationId")
    args = call.get("args")
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            args = {}
    if not isinstance(args, dict):
        args = {}
"""
ANTIGRAVITY_VERDICT = """
    if decision.get("permissionDecision") == "deny":
        return deny(decision.get("permissionDecisionReason") or DENIED)
    if decision.get("decision") in ("deny", "block"):
        return deny(decision.get("reason") or DENIED)
"""
ANTIGRAVITY_STOP = """
    session = event.get("conversationId")
    active = bool(event.get("continuationActive")) or continued(event).exists()
"""
ANTIGRAVITY_CONTINUED = """
def continued(event):
    turn = f"{event.get('conversationId')}\\n{event.get('lastUserInput')}"
    digest = hashlib.sha256(turn.encode("utf-8")).hexdigest()[:24]
    return Path(tempfile.gettempdir()) / "farrier-agy-stop" / digest
"""
ANTIGRAVITY_KEEP_GOING = """
    marker = continued(event)
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
    except OSError:
        pass
    return {"decision": "continue", "reason": reason}
"""
ANTIGRAVITY_BRIDGE_TEXT = render_bridge(
    ANTIGRAVITY_NAMES,
    ANTIGRAVITY_CLAUDE_INPUT + ANTIGRAVITY_CONTINUED,
    ANTIGRAVITY_ARGS,
    '{"decision": "deny", "reason": reason}',
    ANTIGRAVITY_VERDICT,
    ANTIGRAVITY_STOP,
    ANTIGRAVITY_KEEP_GOING,
)
