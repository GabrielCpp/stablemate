# Forces and candidate patterns

Start from the force. A row is a candidate, and the plain answer in the last column
wins whenever the force is weak or absent today.

| Force | Candidate pattern | Plain answer when the force is weak |
|---|---|---|
| One behaviour, several interchangeable variants chosen at run time | Strategy: a role the consumer owns, one implementation per variant, chosen where the system is assembled | One variant today and no second one on the table: a plain function |
| Variants added over time by name, from config or data | Registry keyed by name | A dict literal |
| Ordered stages that each transform a shared result | Pipeline of steps with typed inputs and outputs | Sequential function calls |
| A dependency that must be swapped in tests or by environment | Port (protocol) with adapters, injected at the root | Pass the value in |
| An optional collaborator that callers keep checking for | Null object | Keep it required |
| Construction with many parts or validation before use | Builder or factory function | A constructor with keyword arguments |
| State that moves through named phases with rules on transitions | State machine with an explicit state type | An enum field |
| Many rules that each accept or reject a candidate | Chain of predicates, or specification objects | One function with early returns |
| A score combined from independent terms | Weighted sum of term functions | One function |
| Expensive derived data that rarely changes | Cache keyed by its inputs, stored as data | Recompute |
| The same data read in several shapes by different consumers | Read model or view per consumer | One type, with properties |
| A notification several independent parties react to | Observer or event list | Direct calls |
| A value with rules about its own validity | Value object that validates on construction | A typed field |
| Comparing an output against a reference with a tolerance | Oracle: measure, reference, tolerance, verdict as separate parts | An assertion |
