story: none
date: 2026-11-16
elements: LibraryList, LibraryShow, LibraryCheck, Source, Eject

The library commands are played with `--library lib`, the folder the sandbox seeds with one skill, `demo`, and one
scaffold. The catalog lists the demo skill with the layer it comes from and the scaffold under its own kind, and
`library check` counts one source because a scaffold definition carries no front matter. The sandbox names an empty
base library (`STABLEMATE_BASE_DIR`), which outranks the one farrier ships, so the overlay holds every source.

`farrier source` answers for a file install generated with the library file it came from, and refuses a file that
exists and carries no `metadata.source` or banner. `farrier eject` hands the generated skill folder over: it drops
`- demo` from the `skills:` list of agents.yml, leaves the folder in place without the generated marks, and renders
again, which writes five files because the skill is no longer one of them. Ejecting the same name again finds no
generated skill, and the refusal lists none.
