---
type: concept
slug: okf-builder-shared-vocabulary
title: OKF-builder check vocabulary
---
# OKF-builder check vocabulary

Repair prompts receive their verification grammar from Ostler's live check registry rather than a
hand-maintained list. Each rendered line contains the callable signature and the defect the check
excludes. The same module renders every registered bullet-key type with its flags and the shared
normative keys, allowing a repair turn to author nested nodes without guessing the current schema.

- code: `workflows/src/workhorse_workflows/okf_builder/shared/vocabulary.py`

## Methods

### check_vocabulary
- sig: `check_vocabulary() -> str`
- does: renders every registered check signature and its exclusion rationale, one check per line
- verify: count(subject="rendered OKF-builder check vocabulary", equals=1)
- returns: prompt-ready check vocabulary text
- verify: count(subject="OKF-builder check vocabulary results", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/vocabulary.py::check_vocabulary`

### bullet_grammar
- sig: `bullet_grammar() -> str`
- does: renders the registry's key flags and shared normative keys
- verify: count(subject="rendered OKF-builder bullet grammar headers", equals=1)
- does: renders every registered UI node type and its ordered bullet keys
- verify: count(subject="rendered OKF-builder bullet grammar types", equals=1)
- returns: prompt-ready bullet grammar text
- verify: count(subject="OKF-builder bullet grammar results", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/vocabulary.py::bullet_grammar`
