import { env } from '$env/dynamic/private';

export const headers = { Authorization: 'Bearer test-token' };

export function todoApi(path, init = {}) {
  return (fetch) => fetch(`${env.TODO_API}${path}`, { ...init, headers: { ...headers, ...init.headers } });
}
