# Judge a closed question

You answer one closed question about the texts below. You have no tools and no other input. Answer from these texts alone.

## The question

Kind: **{{ kind }}**

{{ ask }}

## Subjects

Answer once for each key. The value is the text to answer about.

```json
{{ subjects }}
```

## What an answer may name

```json
{{ context }}
```

## Allowed answers

Each answer is exactly one of: {{ answers }}.

When you are not sure of a subject, answer `{{ default }}` for it. A wrong match costs more than a missed one.

{{ result_schema }}
