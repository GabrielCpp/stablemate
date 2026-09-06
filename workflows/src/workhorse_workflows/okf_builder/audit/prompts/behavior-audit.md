# okf-builder - Two-way source evidence audit

Assess this packet in two independent passes. First read the source candidates and
identify externally observable behavior, then decide whether the book describes it.
Second read each book claim and assess its support against the source evidence.
Source citations locate context; they are not evidence that a behavior is documented.
Read the supplied complete enclosing source, including side effects and early guards,
before judging isolated snippets or return values.

- `supported`: all clauses of the claim are consistent with the observed evidence.
- `contradicted`: observed behavior is incompatible with the claim; identify that evidence.
- `partial`: identify a concrete unsupported or incorrect clause with observed counterevidence,
  alongside the supported portion; this means an observed mismatch, not lack of context.
- Insufficient evidence (including absent source) means `unresolved`, with no repair.

Use `missing` only after inspecting the supplied same-node book context, including
non-normative signatures and prose. A structural omission needs an explicit structural reason,
not a claim that documented behavior is absent. If a signature or prose documents the behavior,
use `covered` with an actual supported/partial claim link or `book_evidence` referencing
the exact document lines in `packet.book_context`. For signature-only coverage, cite the
signature's node and inclusive start_line/end_line; do not invent claims or a structural
omission when the existing prose already covers the behavior. This confirms documented
source coverage, not QA proof. Assess normative claims independently; a book span does
not establish their source support.
Use `implementation_detail` only with a concrete reason the candidate is not a public
contract. Explain missing, contradicted, and partial behavior precisely
enough to repair the affected source-file or book node as a coherent unit.

This is a read-only, packet-only assessment. Return JSON directly; do not use tools,
run tests, open a browser, edit files, or seek additional repository context.
The workflow re-extracts source and claims before accepting completion.

Include exactly one verdict for every supplied claim and candidate ID, echo the exact
packet digest, and make links reciprocal in both directions. Supported, contradicted,
and partial claims require candidate links. Covered candidates require a supported or
partial claim link or at least one validated book span. Only covered candidates may carry
book evidence. Implementation details carry neither claim links nor book evidence.
Every book reference must resolve to a supplied node and a nonblank inclusive line range
within that context, without duplicates. The deterministic validator rejects missing or
foreign IDs, stale digests, invalid book spans, and inconsistent links.

## Packet

{{ packet }}

## Validator Feedback

{{ feedback }}

## Output

Produce a JSON document complying with this schema:

{{ result_schema }}
