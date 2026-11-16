import { json } from '@sveltejs/kit';
import { todoApi } from '../../../todo-api.js';

export async function GET({ fetch }) {
  const answer = await todoApi('/users')(fetch);
  return json(await answer.json());
}
