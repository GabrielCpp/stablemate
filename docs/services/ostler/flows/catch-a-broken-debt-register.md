---
type: flow
slug: catch-a-broken-debt-register
title: Catch a broken debt register
---
# Catch a broken debt register

- start: a register record does not parse, and a decision and its evidence records do not name each other back
- steps:
  - [ostler doctor on a broken register](../doctor-checks.md#ostler-doctor-register-links)
- end: the caller reads one finding per broken record or back-link, and the exit status stops a gate
- verify: exit_status(code=1)
- verify: json_path(path="errors", equals=4)
- fixture: [doctor scratch repo](../fixtures/doctor-scratch-repo.md) with a broken register beside an empty book
