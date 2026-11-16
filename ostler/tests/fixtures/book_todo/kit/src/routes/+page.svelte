<script>
  import { enhance } from '$app/forms';
  import { onMount } from 'svelte';
  import { env } from '$env/dynamic/public';

  let { data, form } = $props();
  let ready = $state(false);
  onMount(() => {
    ready = true;
  });

  const names = $derived.by(() => {
    const given = data.users.map((user) => user.name);
    return env.PUBLIC_KIT_BUG === 'handed-order' ? given : [...given].sort();
  });
</script>

<h1>Todos</h1>

<form method="POST" action="?/add" use:enhance data-testid="add-form" data-ready={ready}>
  <label>Title <input name="title" data-testid="title" /></label>
  <label>
    Owner
    <select name="owner" data-testid="owner">
      <option value="">Nobody</option>
      {#each names as name (name)}
        <option value={name}>{name}</option>
      {/each}
    </select>
  </label>
  <button data-testid="add">Add</button>
  {#if form?.error}
    <p data-testid="error">{form.error}</p>
  {/if}
</form>

<a href="/assign" data-testid="to-assign">Assign</a>
