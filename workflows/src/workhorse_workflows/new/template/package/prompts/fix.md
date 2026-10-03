You are working in this repository until the command `{{ check }}` exits 0.

{% if task %}
{{ task }}
{% else %}
Change the code so that `{{ check }}` passes.
{% endif %}

This is round {{ attempt }} of {{ max_rounds }}.
{% if failure %}
The last run of `{{ check }}` failed. Its output, cut to the tail:

```
{{ failure }}
```
{% else %}
Run `{{ check }}` yourself to see what fails.
{% endif %}

Fix the cause, not the check. Do not edit, skip or delete a test to make it pass.

When you are done, reply with one sentence that says what you changed.
