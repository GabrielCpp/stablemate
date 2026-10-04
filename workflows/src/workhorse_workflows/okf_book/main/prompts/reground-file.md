The OKF book of this repository cites `{{ path }}`, and the file has changed since the book
was written. Each node below states claims about the app and cites this file as where they
are grounded. Name the nodes whose claims the change bears on.

You change nothing. Read with your file tools, write no file, and answer only in your reply.

## What changed

The diff from the version the book was written on to the file as it is now{% if diff_left %}, its first lines, with {{ diff_left }} more{% endif %}:

```diff
{{ diff }}
```

- The version the book was written on is kept whole at `{{ old_version }}`.
- The file as it is now is `{{ path }}` in this repository, which you run from.

## The nodes that cite it

{% for cited in nodes %}
{{ cited.number }}. `{{ cited.node }}`{% if cited.symbol %}, citing `{{ cited.symbol }}`{% endif %}

{% endfor %}

A node id is its page's path, then `#` and the node's heading anchor when the node is one
section of the page. Open each page and read what the node claims.

## How to judge

A change bears on a node when a claim the node makes is no longer what the code does, or when
the code now does something the node's reader would need and the node leaves out. Read the
change against the claims. A cited symbol whose own lines did not move can still behave
differently, because what it calls, the type it reads or the configuration around it changed.
Follow the change as far as the node's claims reach.

A change does not bear on a node when it only moves code, renames what the node never names,
edits comments or layout, or touches a part of the file no claim of the node depends on.

When you cannot tell from the diff, read the file as it is now and the kept version. When you
still cannot tell, name the node: a page repair then reads it again, which costs less than a
claim that is wrong.

## Your reply

Reply with one JSON object and nothing else:

```json
{"affected": [{"node": 2, "instruction": "the handler now answers 404 for an archived record, and the node says 403"}]}
```

- `node` is the number of a node in the list above.
- `instruction` says in one or two sentences what changed for that node and what its page
  repair must correct. Quote the code's new behaviour, with the symbol it sits in.
- Leave out every node the change does not bear on. Reply `{"affected": []}` when it bears
  on none.
