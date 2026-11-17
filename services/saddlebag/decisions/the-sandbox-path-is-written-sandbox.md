story: none
date: 2026-11-16
elements: Doctor, Fill, GuardInstall, ChooseDaemon

Programs print absolute paths, and a sandbox is a new directory for every world. The surface writes the sandbox path
as <sandbox> in everything the program printed, so a message built from a path is the same text in every world and the
rules quote it. The daemon's socket is the run directory's saddlebag.sock (saddlebag/saddlebag/sockets.py,
socket_path), and the guard installs into the sandbox's `.claude` or the home's.
