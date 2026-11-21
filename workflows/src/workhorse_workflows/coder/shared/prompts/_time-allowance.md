{% if node_timeout_min != "unbounded" %}
## Time allowance

This turn has {{ node_timeout_min }} minutes. At that mark the run cuts it, keeps this conversation and asks the operator how to go on. Plan the work to fit.
{% endif %}
