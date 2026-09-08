---
type: concept
slug: parity-surveyor-concern-boundaries
title: Parity surveyor concern boundaries
---
# Parity surveyor concern boundaries

`ParitySurveyor` uses `baseline_inventory` and `survey_dir` for different parts of the same
run. Its `setup()` passes both to configuration loading: the baseline identifies the legacy
surfaces under comparison and must name a readable file, while the survey directory determines
where the run's derived inventory, finding records, and manifest live.

Neither input is an implementation to prefer or deprecate. Every parity survey needs a
baseline inventory; callers retain the default survey directory unless they need artifacts in a
different repository-relative location.

- rule: provide `baseline_inventory` for every parity comparison; set `survey_dir` only to override the derived-artifact location, and do not use either input as a replacement for the other
