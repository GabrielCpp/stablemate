<script>
  import { onMount } from 'svelte';
  import { env } from '$env/dynamic/public';

  let { data } = $props();
  let users = $state([]);

  onMount(async () => {
    if (env.PUBLIC_KIT_BUG === 'stray') await fetch('/api/todos');
    const answer = await fetch('/api/users');
    users = await answer.json();
  });

  const names = $derived.by(() => {
    const given = users.map((user) => user.name);
    return env.PUBLIC_KIT_BUG === 'fetched-order' ? given : [...given].sort();
  });
</script>

<h1>Assign</h1>

<p>{data.todos.length} todos</p>

<label>
  Assignee
  <select data-testid="assignee">
    <option value="">Anyone</option>
    {#each names as name (name)}
      <option value={name}>{name}</option>
    {/each}
  </select>
</label>

<a href="/" data-testid="to-home">Back</a>
