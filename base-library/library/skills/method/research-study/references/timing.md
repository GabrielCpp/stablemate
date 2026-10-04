# Timed readings

The full rules for the timed readings of step 4 in [`research-study`](../SKILL.md).

Every timed reading stores the script that took it and the script's hash beside the
number, with the machine's load at the start and the end. A reading whose script changed
after it was taken is void until it is retaken under the new hash. A reading assembled from two scripts names both. A reading that stored no script hash, or no
load at its start and end, is void as well, and this step retakes it. A record that keeps an
old rule's figure beside the figure in force marks the old one superseded, or drops it.

On a machine another process shares, one reading is not a rate. The other process's demand
moves from minute to minute, and one rate read twenty minutes apart can differ thirtyfold.
This step takes repeated short readings spread across a window as long as the work they
price, each with its own load, and records the lowest, the median and the highest. A long
reading and a short one of the same rate are both kept, and the spread covers both. Every
break-even is placed against the whole spread, never against one reading inside it. A rate
the study cannot read at idle while the other process runs stays unread at idle, and the
record says so. It is not filled from an earlier reading that stored no script.

## Deciding rates

Measure here every rate that decides whether a verdict can be read, when one timed unit on
the machine at hand reads it in minutes: a training step, a decoded token at the batch and
context the run will use, one judge run on one case, one sub-check the judge runs. Record
the rate, the unit that read it, its method and its date. Framings cite the measure. A
range stands in for such a rate only when no unit can run before the study's date. A
throughput derived from a peak figure is a deciding rate until a run on the machine reads
it.

## A plan at the measured load

A plan meets its date and its budget at the load the machine has shown, never at a reading
it has not shown during the study. On a shared machine, the plan's calendar time is its
work time divided by the share of the machine the study has had, read from the recorded
loads. A plan that fits only at idle, or only at the best reading in the record, does not
fit. Each training run inside the plan holds its own hours against the training bar at the
same load. When the study chose the date itself and the measured load makes every plan miss
it, that is a finding about the date. The study reports it to the operator with the date
the load gives. It never reprices the plans at idle to make them fit.
