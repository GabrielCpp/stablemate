story: track50
date: 2026-11-11
elements: Install, Scaffold, no_library_to_install, no_library_to_scaffold

A directory is a usable library when it holds a library/ folder, and nothing else is required of it.
`is_library_dir` (farrier/farrier/_vendor/stablemate_core/layout.py:8-10)
tests only `(path / "library").is_dir()`. resolve_library_dir (farrier/farrier/layers.py:122-127) resolves the
path against the working directory and refuses a directory without library/ with the sentence the rules quote.
The book's seed library holds library/ and scaffolds/ and no packs/, so every run proves the tool does not
need packs/.
