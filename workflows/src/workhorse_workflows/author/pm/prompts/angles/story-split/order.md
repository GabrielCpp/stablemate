Judge whether the dependencies between stories are real.

- Each `## Dependencies` entry names a real prerequisite: the blocked story cannot be built or observed without the blocking one.
- No dependency exists only to impose an order. No real prerequisite is missing.
- A story that depends on a sibling for a surface it also builds is a finding that names both stories.
