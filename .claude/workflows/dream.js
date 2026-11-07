export const meta = {
  name: 'dream',
  description: "Check this project's Claude Code memory against recent session transcripts and write a reorganized copy for review",
  whenToUse: 'After a stretch of sessions, to correct, merge, prune and extend the auto memory without touching the live folder',
  phases: [
    { title: 'Scout', detail: 'resolve the memory folder, index its notes, pick the sessions since the last dream' },
    { title: 'Mine', detail: 'read user turns of each session for corrections, decisions and facts' },
    { title: 'Verify', detail: 'check each touched note against transcripts and the repository' },
    { title: 'Sweep', detail: 'check every other note for staleness and mark what can be forgotten' },
    { title: 'Write', detail: 'build the staged memory copy and the dream report' },
  ],
}

const MAX_SESSIONS = (args && args.maxSessions) || 6
const SESSIONS_PER_MINER = 2
const NOTES_PER_VERIFIER = 8
const NOTES_PER_SWEEPER = 15
const SWEEP = !(args && args.sweep === false)

const EXTRACT = `jq -r 'select((.type=="user" or .type=="assistant") and (.isMeta|not)) | .type as $t | .timestamp as $ts | .message.content | if type=="string" then . else (map(select(.type=="text") | .text) | join("\\n")) end | select(length>0) | select(startswith("This session is being continued")|not) | "--- \\($t) \\($ts)\\n\\(.)"' <transcript.jsonl>`

const SCOUT_SCHEMA = {
  type: 'object',
  properties: {
    projectDir: { type: 'string' },
    memoryDir: { type: 'string' },
    lastDream: { type: ['string', 'null'] },
    notes: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          name: { type: 'string' },
          file: { type: 'string' },
          description: { type: 'string' },
        },
        required: ['name', 'file', 'description'],
      },
    },
    sessions: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          path: { type: 'string' },
          modified: { type: 'string' },
        },
        required: ['path', 'modified'],
      },
    },
  },
  required: ['projectDir', 'memoryDir', 'notes', 'sessions'],
}

const CANDIDATES_SCHEMA = {
  type: 'object',
  properties: {
    candidates: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          action: { type: 'string', enum: ['new', 'update', 'contradict'] },
          note: { type: ['string', 'null'] },
          type: { type: 'string', enum: ['user', 'feedback', 'project', 'reference'] },
          claim: { type: 'string' },
          evidence: { type: 'string' },
          session: { type: 'string' },
          date: { type: 'string' },
        },
        required: ['action', 'claim', 'evidence', 'session', 'date'],
      },
    },
  },
  required: ['candidates'],
}

const VERDICTS_SCHEMA = {
  type: 'object',
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          note: { type: ['string', 'null'] },
          outcome: { type: 'string', enum: ['keep', 'rewrite', 'merge', 'delete', 'create'] },
          mergeInto: { type: ['string', 'null'] },
          text: { type: 'string' },
          reason: { type: 'string' },
        },
        required: ['outcome', 'text', 'reason'],
      },
    },
  },
  required: ['verdicts'],
}

const REPORT_SCHEMA = {
  type: 'object',
  properties: {
    stagedDir: { type: 'string' },
    reportFile: { type: 'string' },
    created: { type: 'number' },
    rewritten: { type: 'number' },
    merged: { type: 'number' },
    deleted: { type: 'number' },
    indexLines: { type: 'number' },
  },
  required: ['stagedDir', 'reportFile', 'created', 'rewritten', 'merged', 'deleted', 'indexLines'],
}

function chunk(list, size) {
  const out = []
  for (let i = 0; i < list.length; i += size) out.push(list.slice(i, i + size))
  return out
}

phase('Scout')
const scout = await agent(
  `Resolve this project's Claude Code auto memory and the sessions a dream should read.\n\n` +
  `1. projectDir is ~/.claude/projects/<slug>, where <slug> is the absolute working directory with every "/" and "." replaced by "-". ` +
  `Confirm it exists. memoryDir is projectDir/memory.\n` +
  `2. Read projectDir/dream/last-run.json if it exists and return its "finished" field as lastDream, else null.\n` +
  `3. For every .md file in memoryDir except MEMORY.md, return its frontmatter name, its file name and its description.\n` +
  `4. List projectDir/*.jsonl by modification time, newest first. Keep those modified after lastDream, at most ${MAX_SESSIONS}. ` +
  `Skip the newest one when it was modified in the last 10 minutes, because that is the session running this dream.\n` +
  `Return absolute paths. Use ISO 8601 for times.`,
  { schema: SCOUT_SCHEMA, phase: 'Scout', label: 'scout', effort: 'low' }
)

const noteIndex = scout.notes.map(n => `- ${n.name} (${n.file}): ${n.description}`).join('\n')
log(`${scout.notes.length} notes, ${scout.sessions.length} session(s) since ${scout.lastDream || 'the first session'}`)
if (!scout.sessions.length && !SWEEP) return { scout, report: null }

phase('Mine')
const mined = !scout.sessions.length ? [] : await pipeline(
  chunk(scout.sessions, SESSIONS_PER_MINER),
  group => agent(
    `You read Claude Code session transcripts to find what a future session should remember.\n\n` +
    `Transcripts:\n${group.map(s => `- ${s.path} (modified ${s.modified})`).join('\n')}\n\n` +
    `Read each with this command, which keeps only the text of user and assistant turns:\n${EXTRACT}\n` +
    `Pipe it through less, head, sed -n or grep. Do not cat a whole raw .jsonl file. Read every user turn. ` +
    `Read assistant turns where a user turn reacts to them.\n\n` +
    `Existing memory notes:\n${noteIndex}\n\n` +
    `Return a candidate for each of these:\n` +
    `- a correction or a preference the user stated about how to work (type feedback),\n` +
    `- a decision the user settled, a goal or a constraint on ongoing work, with an absolute date (type project),\n` +
    `- a fact about the user (type user), or a pointer to an outside resource (type reference),\n` +
    `- a statement that contradicts or outdates an existing note (action contradict or update, note set to its name).\n` +
    `Skip what the repository or git history already records, and what only mattered inside that session. ` +
    `evidence is a short quote of the user's own words with its timestamp. A candidate without a quote is not a candidate.`,
    { schema: CANDIDATES_SCHEMA, phase: 'Mine', label: `mine:${group.length} session(s)` }
  )
)
const candidates = mined.filter(Boolean).flatMap(r => r.candidates)
log(`${candidates.length} candidate(s): ${candidates.filter(c => c.action === 'new').length} new, ${candidates.filter(c => c.action !== 'new').length} touching existing notes`)

phase('Verify')
const touched = [...new Set(candidates.map(c => c.note).filter(Boolean))]
const units = [
  ...touched.map(name => ({ note: name, candidates: candidates.filter(c => c.note === name) })),
  ...candidates.filter(c => !c.note).map(c => ({ note: null, candidates: [c] })),
]
const untouched = scout.notes.filter(n => !touched.includes(n.name))
const swept = SWEEP ? pipeline(
  chunk(untouched, NOTES_PER_SWEEPER),
  batch => agent(
    `You decide which notes in a Claude Code memory folder at ${scout.memoryDir} are stale and can be forgotten. ` +
    `Each memory file holds one fact, with frontmatter (name, description, metadata.type). Notes link each other with [[name]].\n\n` +
    `All notes:\n${noteIndex}\n\n` +
    `Notes to judge:\n${batch.map(n => `- ${n.name} (${n.file})`).join('\n')}\n\n` +
    `Read each note to judge. Check what it claims against the repository: the files, functions, flags, commands and commits it names, ` +
    `with git log, git show and grep. Today's date comes from date -u.\n\n` +
    `A note can be forgotten (delete) when one of these holds, and you can show which:\n` +
    `- it tracks a temporary state that has ended: a run stopped and never restarted, a cleanup that was done, a wait whose condition passed;\n` +
    `- it is a progress snapshot of work that has finished;\n` +
    `- everything it names is gone from the repository and the lesson only applied to those things;\n` +
    `- the repository, its git history or a checked-in instruction file now records the same fact.\n` +
    `A note that another note in the index duplicates is a merge, with mergeInto the survivor. ` +
    `A note that still holds but carries an outdated detail is a rewrite with the full new file as text.\n` +
    `Age alone never makes a note stale. A user or feedback note stays unless something newer contradicts it. ` +
    `A finished run or project does not make a note stale when the note carries a measured baseline or a method other notes still judge against. ` +
    `When the evidence is unclear, keep the note.\n\n` +
    `Return one verdict per note, with note set to its name and the reason in one sentence naming the evidence.`,
    { schema: VERDICTS_SCHEMA, phase: 'Sweep', label: `sweep:${batch.length} note(s)` }
  )
) : Promise.resolve([])
const verified = await pipeline(
  chunk(units, NOTES_PER_VERIFIER),
  batch => agent(
    `You judge proposed changes to a Claude Code memory folder at ${scout.memoryDir}. Each memory file holds one fact, ` +
    `with frontmatter (name, description, metadata.type) and, for feedback and project notes, **Why:** and **How to apply:** lines. ` +
    `Notes link each other with [[name]].\n\n` +
    `Existing notes:\n${noteIndex}\n\n` +
    `Units to judge:\n${JSON.stringify(batch, null, 2)}\n\n` +
    `For each unit with a note, read that note file. Check every candidate against the quoted evidence. Rerun the transcript command when a quote looks out of context:\n${EXTRACT}\n` +
    `When a note or candidate names a file, function, flag or commit, check that it still exists in the repository.\n\n` +
    `Return one verdict per unit:\n` +
    `- keep: the note stands as written.\n` +
    `- rewrite: text is the full new file, frontmatter included. The newest dated statement wins over an older one.\n` +
    `- merge: the note duplicates another. mergeInto names the survivor, and text is the survivor's full new file.\n` +
    `- delete: the note is wrong or no longer true, and nothing replaces it.\n` +
    `- create: a new note from a candidate with no note. text is the full file. Check first that no existing note covers it, and rewrite that note instead when one does.\n` +
    `Reject a candidate whose evidence does not support it. Give the reason in one sentence.`,
    { schema: VERDICTS_SCHEMA, phase: 'Verify', label: `verify:${batch.length} unit(s)` }
  )
)
const sweptResults = await swept
const verdicts = [...verified, ...sweptResults].filter(Boolean).flatMap(r => r.verdicts)
log(`Sweep marked ${sweptResults.filter(Boolean).flatMap(r => r.verdicts).filter(v => v.outcome === 'delete').length} note(s) to forget`)
const changes = verdicts.filter(v => v.outcome !== 'keep')
log(`${changes.length} change(s) from ${verdicts.length} verdict(s)`)

phase('Write')
const report = await agent(
  `Build a staged copy of a Claude Code memory folder. Never modify ${scout.memoryDir} itself.\n\n` +
  `1. Run date -u +%Y%m%dT%H%M%SZ to get a stamp. stagedDir is ${scout.projectDir}/dream/<stamp>/memory. Copy ${scout.memoryDir} there with cp -a.\n` +
  `2. Apply these verdicts in stagedDir. rewrite and create write text to the note's file (a new note gets <name>.md). ` +
  `merge writes text to the mergeInto file and deletes the merged note. delete removes the file.\n` +
  `${JSON.stringify(changes, null, 2)}\n` +
  `3. Update stagedDir/MEMORY.md: one line per note, "- [Title](file.md) — hook". Drop lines of deleted or merged notes, add lines for created ones, ` +
  `reword the hook of rewritten ones. Keep the file under 200 lines. Replace any [[name]] link that points at a merged note with its survivor, ` +
  `and turn a [[name]] link that points at a deleted note into plain text.\n` +
  `4. Write ${scout.projectDir}/dream/<stamp>/REPORT.md: for each change, the note, the outcome and the reason. ` +
  `5. Write ${scout.projectDir}/dream/<stamp>/last-run.json with {"finished": "<ISO 8601 now>", "staged": "<stagedDir>", "sessions": [the transcript paths]}.\n` +
  `6. End REPORT.md with the one command that applies the dream: rsync -a --delete <stagedDir>/ ${scout.memoryDir}/ && cp ${scout.projectDir}/dream/<stamp>/last-run.json ${scout.projectDir}/dream/last-run.json\n` +
  `Transcripts read: ${JSON.stringify(scout.sessions.map(s => s.path))}`,
  { schema: REPORT_SCHEMA, phase: 'Write', label: 'write', effort: 'low' }
)

return { scout: { memoryDir: scout.memoryDir, lastDream: scout.lastDream, sessions: scout.sessions.length }, candidates: candidates.length, changes, report }
