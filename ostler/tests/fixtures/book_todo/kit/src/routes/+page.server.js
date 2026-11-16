import { fail } from '@sveltejs/kit';
import { todoApi } from '../todo-api.js';

export async function load({ fetch }) {
  const answer = await todoApi('/users')(fetch);
  return { users: await answer.json() };
}

export const actions = {
  add: async ({ request, fetch }) => {
    const form = await request.formData();
    const body = { title: String(form.get('title') ?? '') };
    const owner = String(form.get('owner') ?? '');
    if (owner) body.assignee = owner;
    const answer = await todoApi('/todos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })(fetch);
    if (!answer.ok) return fail(answer.status, { error: (await answer.json()).error });
    return { added: true };
  }
};
