"""The TypeScript that OpenCode and Pi run to call each guard before a tool, built from one template."""

from __future__ import annotations

IMPORT = 'import { spawn } from "node:child_process"\n'

GUARD_TABLE = "\nconst GUARDS = @GUARDS@\n"

COMMON = """
function verdict(code, stdout, stderr) {
  if (code === 2) return { deny: stderr.trim() || "Denied by a guard." }
  try {
    const decision = JSON.parse(stdout).hookSpecificOutput
    if (decision?.permissionDecision === "deny") {
      return { deny: decision.permissionDecisionReason || "Denied by a guard." }
    }
    if (decision?.updatedInput && typeof decision.updatedInput === "object") {
      return { updated: decision.updatedInput }
    }
  } catch {}
  return {}
}

function ask(guard, call) {
  return new Promise((resolve) => {
    const child = spawn("sh", ["-c", guard.command], { timeout: guard.timeout * 1000 })
    let stdout = ""
    let stderr = ""
    child.stdout.on("data", (chunk) => (stdout += chunk))
    child.stderr.on("data", (chunk) => (stderr += chunk))
    child.on("error", () => resolve({}))
    child.on("close", (code) => resolve(verdict(code, stdout, stderr)))
    child.stdin.on("error", () => {})
    child.stdin.end(call)
  })
}
"""

OPENCODE_SHAPES = """
const SHAPES = {
  bash: (args) => ["Bash", { command: args.command, timeout: args.timeout }],
  read: (args) => ["Read", { file_path: args.filePath }],
  grep: (args) => ["Grep", { pattern: args.pattern, path: args.path }],
  write: (args) => ["Write", { file_path: args.filePath, content: args.content }],
  edit: (args) => [
    "Edit",
    {
      file_path: args.filePath,
      old_string: args.oldString,
      new_string: args.newString,
      replace_all: args.replaceAll,
    },
  ],
  apply_patch: (args) => ["apply_patch", { command: args.patchText }],
}

const REWRITES = {
  bash: (args, updated) => {
    if (typeof updated.command === "string") args.command = updated.command
    if (typeof updated.timeout === "number") args.timeout = updated.timeout
  },
}
"""

OPENCODE_PLUGIN = """
export const FarrierGuards = async ({ directory }) => ({
  "tool.execute.before": async (input, output) => {
    const shape = SHAPES[input.tool]
    if (!shape) return
    for (const guard of GUARDS) {
      if (!guard.tools.includes(input.tool)) continue
      const [tool_name, tool_input] = shape(output.args)
      const call = JSON.stringify({
        hook_event_name: "PreToolUse",
        session_id: input.sessionID,
        cwd: directory,
        tool_name,
        tool_input,
      })
      const result = await ask(guard, call)
      if (result.deny) throw new Error(result.deny)
      if (result.updated && REWRITES[input.tool]) REWRITES[input.tool](output.args, result.updated)
    }
  },
})
"""

PI_TOOLS = """
const TOOLS = {
  bash: (input) => [["Bash", { command: input.command }]],
  read: (input) => [["Read", { file_path: input.path }]],
  write: (input) => [["Write", { file_path: input.path, content: input.content }]],
  grep: (input) => [["Grep", { pattern: input.pattern, path: input.path }]],
  find: (input) => [["Glob", { pattern: input.pattern, path: input.path }]],
  edit: (input) =>
    (input.edits ?? []).map((edit) => [
      "Edit",
      { file_path: input.path, old_string: edit.oldText, new_string: edit.newText },
    ]),
}
"""

PI_EXTENSION = """
export default function (pi) {
  pi.on("tool_call", async (event, ctx) => {
    const calls = TOOLS[event.toolName]?.(event.input)
    if (!calls) return
    for (const guard of GUARDS) {
      if (!guard.tools.includes(event.toolName)) continue
      for (const [tool_name, tool_input] of calls) {
        const call = JSON.stringify({
          hook_event_name: "PreToolUse",
          session_id: ctx.sessionManager.getSessionId(),
          cwd: ctx.cwd,
          tool_name,
          tool_input,
        })
        const result = await ask(guard, call)
        if (result.deny) return { block: true, reason: result.deny }
        if (result.updated && event.toolName === "bash" && typeof result.updated.command === "string") {
          event.input.command = result.updated.command
        }
      }
    }
  })
}
"""

OPENCODE_BRIDGE = IMPORT + GUARD_TABLE + OPENCODE_SHAPES + COMMON + OPENCODE_PLUGIN
PI_BRIDGE = IMPORT + PI_TOOLS + GUARD_TABLE + COMMON + PI_EXTENSION
