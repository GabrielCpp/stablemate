story: track50
date: 2026-11-11
elements: Init, Install, Scaffold, FileRecord

Programs print absolute paths, and a sandbox is a new directory for every world. The surface writes the sandbox
path as <sandbox> in everything the program printed, so a message built from a path is the same text in every
world and the rules quote it. The directory is named acme because farrier prefixes the skills it installs with the
kebab-cased name of the repository's directory (farrier/farrier/naming.py, repo_prefix), so the skill lands at
.claude/skills/acme-demo.
