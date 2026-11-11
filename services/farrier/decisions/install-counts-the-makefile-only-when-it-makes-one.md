story: track50
date: 2026-11-11
elements: Install

The number install prints is four launcher files, one skill file for each selected skill, and the root Makefile
only when the repository has none. The renderer adds the Makefile to its outputs when the path does not exist
(farrier/farrier/renderer.py:769-771) and the count is the size of that map (farrier/farrier/cli.py:289). A
second install of the same repository therefore prints one fewer than the first. Where the repository already has
a Makefile, install appends the include block to it and prints a line about that (farrier/farrier/outputs.py:707).
