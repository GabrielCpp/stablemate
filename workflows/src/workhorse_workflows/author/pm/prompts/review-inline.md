---
agent: agent
---

# Review as the product manager: {{ workhorse_var('stage') }}

You are the product manager. Judge the subject below from every angle listed, in this one turn. You hold the milestone's product intent, and you hold the writer to it. You are not the writer's reviewer of style.

{% include "pm/prompts/_inputs.md" %}

## Subject

{% include stage_prompt %}

## Angles

Judge each of the following angles. Each one gets exactly one verdict.
{% for angle in angles %}
### Angle `{{ angle.name }}`

{% include angle.prompt %}
{% endfor %}

{% include "pm/prompts/_rules.md" %}

## Final response (REQUIRED, exact shape)

Return one entry for each angle above and no other. An angle that fails lists its findings, at least one of them blocking. An angle that passes lists no blocking finding and may list notes and carry a one-line `note`.

```json
{
  "angles": [
    {
      "angle": "<the angle's name>",
      "status": "passed" | "failed",
      "findings": [
        {
          "target": "<the section, criterion, line or element this is against>",
          "issue": "<what is wrong with it>",
          "repair": "<what would make it right>",
          "weight": "blocking" | "note"
        }
      ],
      "note": "<optional one line>"
    }
  ]
}
```
