import { todoApi } from '../../todo-api.js';

export async function load({ fetch }) {
  const answer = await todoApi('/todos')(fetch);
  return { todos: await answer.json() };
}
