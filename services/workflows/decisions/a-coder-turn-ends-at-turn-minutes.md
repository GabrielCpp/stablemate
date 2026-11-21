story: none
date: 2026-11-21
elements: DryRunCoder
sources: workflows/src/workhorse_workflows/coder/main/flow.py::Coder, workflows/src/workhorse_workflows/coder/shared/owner.py::cut_notes

Every owner turn and every resolver turn of the coder runs for at most `turn_minutes` minutes, 60 unless the launch
says otherwise. The same value is the turn's pacing advice and its wall-clock deadline. The prompt tells the turn its
minutes, and the run cuts it at that mark.

A turn that is cut keeps its conversation, and the lane asks the operator how to go on. It never goes to the resolver,
because the resolver turn has the same allowance and would cost another hour on the same question. The operator's answer
starts the turn again on the same conversation, with the answer in hand. A merge turn that is cut asks the operator
without commenting on the pull request, because a cut is the allowance running out and not a refused merge.

`turn_minutes` must be a whole number above zero. A launch that gives any other value is refused before any turn starts,
and it names `turn_minutes`. A run resumed from a checkpoint that predates the parameter takes the default of 60.
