story: workhorse-book
date: 2026-11-12
elements: Run

The runner prints the paths of the run directory it works in, and the surface writes the sandbox path back as `<sandbox>` in everything the program printed. The seed names the directory `acme` so the working directory the runner resolves, its basename, is the same in every world. Paths a message prints are written `<sandbox>/.agents/runs/loop-runner-<name>`.
