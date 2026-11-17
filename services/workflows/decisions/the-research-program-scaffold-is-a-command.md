story: workflows-book
date: 2026-11-17
elements: NewProgram, FileRecord

The research workflow's README tells a person to run python -m workhorse_workflows.research.scaffold.new_program
before the first run. It is a command with its own arguments, so the book plays it as one: the program folder, the
source folder, the first gate, --set-default and --force. The flags that only fill the manifest's machine envelope
(--repo, --name, --progress, --result-branch, --ram-gb, --cpus, --gpu, --disk-gb, --min-containment) are not played.
The watch names the one folder the book stamps, specs/demo, and its two gates G0 and G1, so the program's name and
source folder are the same in every cell. The folder and gate fields ignore case and surrounding spaces because
another spelling is another path. The scaffolder also prints a line when it creates the empty findings folder, which
the watch cannot see, so that line is left out of the comparison.
