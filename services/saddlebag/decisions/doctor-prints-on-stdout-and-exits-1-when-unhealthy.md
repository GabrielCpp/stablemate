story: none
date: 2026-11-16
elements: Doctor

doctor prints its report and exits 1 while the store is unreachable or a secret holds no value (saddlebag/saddlebag/
cli.py, cmd_doctor). The book declares the exit-1 answer as a refusal read from stderr, which is empty, so the report of an
unhealthy store is not compared. A healthy report is compared line for line.
