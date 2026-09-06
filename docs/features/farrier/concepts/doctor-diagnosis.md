---
type: concept
slug: doctor-diagnosis
title: Repository diagnosis
---
# Repository diagnosis

`farrier doctor` reports declarations that leave workflow gates unavailable. It warns about
omissions but only exits nonzero when `agents.yml` cannot be read.

### method: Finding
- sig: `Finding(level: str, message: str)`
- does: carry one diagnostic severity and operator-facing message
- code: `farrier/farrier/doctor.py::Finding`
- verify: count(subject="repository diagnostic records", equals=1)

## Methods

### method: _services_block
- sig: `_services_block(config: dict[str, Any]) -> dict[str, Any]`
- does: select the top-level services mapping or the mapping nested under workflow
- returns: an empty mapping when neither value is a mapping
- verify: count(subject="service mappings selected from configuration", equals=1)
- code: `farrier/farrier/doctor.py::_services_block`

### method: diagnose
- sig: `diagnose(repo: Path) -> list[Finding]`
- does: report missing config, invalid YAML, absent workspace roots or markers, missing service gates, and undeclared service roots
- returns: findings without raising for a readable but incomplete configuration
- verify: count(subject="diagnostic findings for an incomplete repository config", equals=1)
- code: `farrier/farrier/doctor.py::diagnose`

### method: report
- sig: `report(repo: Path) -> int`
- does: print each finding and an error/warning summary
- returns: `1` only when an error finding exists, otherwise `0`
- verify: exit_status(code=0)
- code: `farrier/farrier/doctor.py::report`
