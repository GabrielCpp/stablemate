## Step cost

Every step you take resends this whole conversation, so the number of steps is what this turn
costs. Send the reads and commands that do not depend on each other in one message. Chain the
shell commands that depend on each other into one command. Read a file once, whole, instead of
in slices.

A question that would take you three or more steps to answer, such as where something lives,
what calls it or what a log says, goes to a lookup subagent: the agent named `lookup` when your
harness offers one. Its conversation is short and runs on a cheaper model. Ask it for the answer
and the paths and lines it rests on, not for the files.
