---
type: fixture
slug: qa-browser-scratch-plan
title: qa browser scratch plan
---
# qa browser scratch plan

Adds a second plan beside the one [the qa scratch repo](qa-scratch-repo.md) seeds under
`art/specs/s1/`, so a run against the same scratch book can also target a `driver="playwright"`
target. The plan declares no `base_url`, so the target carries nothing to probe before ostler
opens its browser, and the one scenario's `covers` stays empty, since the point is the lifecycle
a `playwright` target opens, not a claim this plan proves about the demo book.

## Steps

### write-browser-plan

- kind: seed
- run: printf -- 'from ostler_qa import Qa, plan, scenario, target\n\nplan(run_id="qa-s1-pw", story="s1")\n\nbrowser = target("browser", driver="playwright")\n\n\n@scenario(target=browser, mechanism="live")\ndef browser_opens(qa: Qa) -> None:\n    """A playwright target hands the scenario a live page before its body runs."""\n    qa.check("page_is_open", qa.browser_page is not None, actual=qa.browser_page is not None, expected=True)\n' > qa-scratch/art/specs/s1/qa_plan_browser.py
