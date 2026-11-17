story: workflows-book
date: 2026-11-12
elements: DryRunCoder, DryRunOkfBook, InstallSkills

The okf-book workflow has four prompts that name a skill (ostler-book): the python book writer, the screen
skeleton and screen reason writers and the catch-up writer. The coder workflow names a skill only
behind a check that the skill is installed, so its dry run passes without one.
Before it starts, the engine resolves each name against the repository's .claude/skills and the home directory,
prints the unresolved ones, one line per prompt, as a WARNING and again as an ERROR on standard output, and exits 1. The other
workflows name no unguarded skill, so their dry run passes in a bare directory. The sandbox home is empty, so a skill is
installed only when the scene puts it under .claude/skills. The book plays the skill installed or not.
