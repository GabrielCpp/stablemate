A finding that reports wrong behaviour is a defect until a test says otherwise. So a "not a
defect" verdict on one cites a test that drives the finding's own case and passes.

You decide on its verdicts. The ones you judge real go to fixers, grouped so no two fixers
share a file.{% if has_skill("isolating-causes") and has_skill("root-cause") %} Each fixer
loads {{ skill_command("isolating-causes") }} and {{ skill_command("root-cause") }}.{% endif %}
A fixer turns the finding into a failing test first. Then it runs every case the criterion's
clause covers, not only the case the finding reports. Before the edit, it writes why the fix
is needed, the decision that caused it, and how that decision could have been prevented,
until the answer is the property the criterion states. A fix that adds a branch, a count or
a check for the reported case alone is handling. It clears this finding and leaves the next
case for QA to find. Findings whose chains meet are one fix.

A fix lands at the cause, with the test that covers it, and each fix is its own commit with
its chain in the commit body.
