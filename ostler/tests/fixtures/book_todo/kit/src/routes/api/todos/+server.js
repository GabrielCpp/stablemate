import { json } from '@sveltejs/kit';
import { todoApi } from '../../../todo-api.js';

export async function GET({ fetch }) {
  const answer = await todoApi('/todos')(fetch);
  return json(await answer.json());
}
