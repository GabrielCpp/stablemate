story: none
date: 2026-11-16
elements: Exec

The book runs `printenv NAME` under exec. Its output is the variable's value and nothing else, so the claim is about
what exec handed the child and what it let through. A variable exec did not hand the child is unset, printenv exits 1
with nothing on stderr, and exec passes that exit code through (cmd_exec, redact.py relay). A program that does not
exist is exit 127 with the program's name.
