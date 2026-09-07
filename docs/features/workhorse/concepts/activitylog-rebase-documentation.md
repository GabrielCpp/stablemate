---
type: concept
slug: activitylog-rebase-documentation
title: ActivityLog rebase documentation
---
# ActivityLog rebase documentation

`ActivityLog.rebase` is the sole method declared in
`workhorse/workhorse/pyflow/activity.py` for replacing workflow base labels and
republishing the sticky activity label. Its two method entries are complementary
documentation views, not alternative implementations: the activity-labels entry
explains flagged-log label behavior, while the pyflow-activity entry explains the
state-transition lifecycle.

- code: `workhorse/workhorse/pyflow/activity.py::ActivityLog.rebase`
- rule: Choose the entry whose surrounding concept matches the question; neither entry ranks above the other or selects a different implementation.
