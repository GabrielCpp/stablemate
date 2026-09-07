---
type: concept
slug: pyflow-registry
title: pyflow workflow registry
---
# pyflow workflow registry

`Registry` is the composition root carried by a workflow console script. It owns the
workflow name, merged node index, named flow classes, entry class, package directory
and dry-run agent replies. A flow class is claimed by one registry so handoffs can
recover that flow's own prompts and node substitutions. The registry is composed by
the workflow module and passed to the CLI binding; it does not import or construct the
CLI callable itself. Its explicit `package` is the prompt root when supplied, otherwise
the entry class's import package supplies the root.

- code: `workhorse/workhorse/pyflow/registry.py::Registry`
- tests: [pyflow tests](../../../../workhorse/tests/test_pyflow.py)

## Methods

### Registry.__init__
- sig: `Registry(name: str = "", package: str | None = None)`
- does: creates an empty registry
- verify: created(subject="the workflow registry")
- verify: count(subject="blueprints in a newly constructed registry", equals=0)
- does: records the module that constructed it in `module`
- verify: json_path(path="$.registry.module", matches="^test_pyflow$")
- returns: the registry instance
- verify: json_path(path="$.registry.name", equals="demo")
- code: `workhorse/workhorse/pyflow/registry.py::Registry.__init__`

### Registry.add_blueprints
- sig: `add_blueprints(*blueprints: Blueprint) -> Registry`
- does: appends each blueprint to the registry's blueprint collection
- does: merges each blueprint's live node names and aliases into the registry node index
- raises: `WorkflowDefinitionError` when merged names or aliases collide
- returns: this registry for composition
- verify: count(subject="nodes in a registry after merging one blueprint", equals=1)
- code: `workhorse/workhorse/pyflow/registry.py::Registry.add_blueprints`

### Registry.add_flows
- sig: `add_flows(**flows: type[Workflow]) -> Registry`
- does: rejects a flow name already registered on this registry
- does: rejects each candidate that is not a `Workflow` subclass
- does: claims each workflow class for this registry
- does: registers each claimed class under its supplied flow name
- raises: `WorkflowDefinitionError` for duplicate flow names or non-Workflow classes
- raises: `WorkflowDefinitionError` when a class is already claimed by another registry
- returns: this registry
- verify: count(subject="named flows after registering one flow", equals=1)
- code: `workhorse/workhorse/pyflow/registry.py::Registry.add_flows`
- tests: `workhorse/tests/test_pyflow.py::test_a_flow_class_may_belong_to_only_one_registry`

### Registry.stub_agents
- sig: `stub_agents(replies: dict[str, Any]) -> Registry`
- does: updates dry-run agent replies by prompt stem
- returns: this registry
- verify: count(subject="configured dry-run agent stubs after adding one reply", equals=1)
- code: `workhorse/workhorse/pyflow/registry.py::Registry.stub_agents`
- tests: `workhorse/tests/test_pyflow.py::test_a_dry_run_answers_a_prompt_with_the_reply_the_registry_declared`

### Registry.override
- sig: `override(**by_name: Callable) -> NameIndex[NodeSpec]`
- does: rejects each requested replacement whose node name is not registered
- does: returns a non-mutating node-index copy with requested implementations replaced
- raises: `WorkflowDefinitionError` when a requested node is not registered
- returns: substituted node index
- verify: count(subject="live names in an overridden node index", equals=1)
- code: `workhorse/workhorse/pyflow/registry.py::Registry.override`
- tests: `workhorse/tests/test_pyflow.py::test_the_run_index_supplies_the_body_the_callsite_only_names`
- tests: `workhorse/tests/test_pyflow.py::test_overriding_a_node_the_registry_does_not_have_names_the_registered_ones`

### Registry.entry_point
- sig: `entry_point(entry: type[Workflow]) -> Registry`
- does: rejects an entry that is not a `Workflow` subclass
- does: rejects a registry whose name is empty
- does: claims and stores the entry class
- does: registers the entry class under the `default` flow name
- returns: this registry for console-script binding
- verify: count(subject="default flow names after declaring an entry point", equals=1)
- code: `workhorse/workhorse/pyflow/registry.py::Registry.entry_point`
- tests: `workhorse/tests/test_pyflow.py::test_entry_point_declares_the_default_flow_and_chains`
- tests: `workhorse/tests/test_pyflow.py::test_a_registry_without_a_name_cannot_be_a_command`

### Registry.flow
- sig: `flow(flow_name: str | None) -> type[Workflow]`
- does: selects the entry class when `flow_name` is empty or `None`
- does: selects the class registered under a non-empty flow name
- raises: `WorkflowDefinitionError` when no entry exists for an empty flow name
- raises: `WorkflowDefinitionError` when a non-empty flow name is unknown
- verify: exit_status(code=1)
- returns: the selected workflow class
- code: `workhorse/workhorse/pyflow/registry.py::Registry.flow`

### Registry.directory
- sig: `directory() -> Path`
- does: resolves the explicitly configured package when one is present
- does: resolves the entry class's import package when no package is configured
- raises: `WorkflowDefinitionError` when neither a package nor an entry point is available
- raises: `WorkflowDefinitionError` when the entry class has no package directory
- verify: exit_status(code=1)
- returns: the real package directory used as the prompt root
- code: `workhorse/workhorse/pyflow/registry.py::Registry.directory`
- tests: `workhorse/tests/test_console_script.py::test_a_declared_package_is_the_directory`
- tests: `workhorse/tests/test_console_script.py::test_a_registry_with_a_package_needs_no_entry_point`
- tests: `workhorse/tests/test_console_script.py::test_zip_imported_package_fails_at_startup`

### Registry.flow_names
- sig: `flow_names() -> list[str]`
- returns: registered flow names in sorted order
- verify: count(subject="default flow names after declaring an entry point", equals=1)
- code: `workhorse/workhorse/pyflow/registry.py::Registry.flow_names`
- tests: `workhorse/tests/test_pyflow.py::test_entry_point_declares_the_default_flow_and_chains`

### Registry.class_named
- sig: `class_named(class_name: str | None) -> type[Workflow] | None`
- does: searches registered flows by workflow class name when a class name is supplied
- returns: the matching registered workflow class, or `None` when the input is empty or unmatched
- verify: json_path(path="$.registry", absent=true)
- code: `workhorse/workhorse/pyflow/registry.py::Registry.class_named`
- tests: `workhorse/tests/test_pyflow.py::test_entry_point_declares_the_default_flow_and_chains`

### Registry.state
- sig: `state(fn: Callable[..., Any] | None = None, *, aliases: Iterable[str] = ()) -> Any`
- does: provides the registry-bound spelling of the standalone state decorator
- verify: count(subject="state decorators applying the supplied aliases", equals=1)
- returns: the decorated state function or a decorator when called without a function
- verify: count(subject="state functions or decorators returned by Registry.state", equals=2)
- code: `workhorse/workhorse/pyflow/registry.py::Registry.state`

### registry_of
- sig: `registry_of(cls: type[Workflow]) -> Registry | None`
- returns: the registry directly claiming the class, or `None` for an unclaimed subclass
- verify: json_path(path="$.registry", absent=true)
- code: `workhorse/workhorse/pyflow/registry.py::registry_of`
