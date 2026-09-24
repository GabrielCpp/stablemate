Write the contract of each file below. A contract says what the file is for, what it
promises its callers, and what it refuses them.

A user drives the product only through these entry points:

{% for entry in entry_points %}
- {{ entry }}
{% endfor %}
{% if entry_points_left_out %}
- and {{ entry_points_left_out }} more, left out of this prompt for its budget
{% endif %}

Each file's whole body is here. So are the names its direct imports declare, without their
bodies. Read nothing else. Do not edit any file.

{% for file in files %}
## `{{ file.file }}`

{% if file.imports %}
Its imports declare:

{% for line in file.imports %}
- {{ line }}
{% endfor %}

{% endif %}
{% if file.problems %}
Your last contract for this file was refused:

{% for problem in file.problems %}
- {{ problem }}
{% endfor %}

{% endif %}
```
{{ file.body }}
```

{% endfor %}
Rules for each contract:

- `file` is the path exactly as its heading gives it.
- `purpose` is one or two sentences on what the file does for the product, in the words a
  user of the product would recognise.
- Each promise and each refusal is one claim that could be demonstrated against the
  running product: an effect, a guard, an output, an error, an exit code. Write the
  behaviour, not how the code is written.
- One `verify` observes the whole claim. A claim that names two commands, two outputs or
  "any" command is several claims, so write each one: "adding an expense with `--dry-run`
  leaves the ledger unchanged" and "importing with `--dry-run` leaves the ledger unchanged",
  not both in one. An output that holds several facts is one claim per fact: "the summary
  prints the entry count" and "the summary prints the total", each with a check that reads
  its own fact, not one claim whose check matches the first line.
- State each claim as what a user sees through an entry point above. A file no user calls
  directly promises what its callers' entry points show because of it: "recording an expense
  with an amount of 0 exits 2", not "`add_entry` raises on a zero amount". A function's
  return value is not a claim, because no user sees it.
- A file that declares nothing and runs nothing, such as a module holding only a docstring or a
  package manifest, promises nothing. Leave its `promises` empty, and say in `purpose` what it
  sets up.
- `symbol` names the function, class, method or constant in this file that carries the
  claim. It must be declared in this file. A re-export is not a declaration. Leave it
  empty only when no symbol carries the claim.
- A check sees only what its line below says it reads. On a cli, that is the exit code, the
  output streams, which files appear, vanish or change, and what a file it left holds. A claim
  about what a file holds is read by `contents`, or by `json_path` or `count` with `file=`
  naming that file. When no check reads the claim, leave `verify` empty rather than pick a
  check that reads something else.
- `verify` is the check that would observe the claim, as `name(arg=value)`, or empty when
  none fits. Every argument is a literal, and a string is quoted:
  `created(subject="ledger.txt")`. A check marked "one of" takes exactly one of the arguments
  it names. Use only these checks, with these signatures:

{% for check in checks %}
  - {{ check }}
{% endfor %}

Reply with only this JSON object, one contract per file above:

```json
{
  "contracts": [
    {
      "file": "src/ledger.py",
      "purpose": "Keeps the ledger file a user adds entries to.",
      "promises": [
        {"text": "Adding the first entry creates the ledger file.", "symbol": "add_entry", "verify": "created(subject=\"ledger.txt\")"}
      ],
      "refusals": [
        {"text": "An amount that is not a number is refused with exit code 2.", "symbol": "parse_amount", "verify": "exit_status(code=2)"}
      ]
    }
  ]
}
```
