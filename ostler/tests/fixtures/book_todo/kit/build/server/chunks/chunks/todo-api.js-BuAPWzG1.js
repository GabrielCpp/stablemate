import { b as private_env } from './shared-server.js-B16pR-90.js';

// src/todo-api.js
var headers = { Authorization: "Bearer test-token" };
function todoApi(path, init = {}) {
	return (fetch) => fetch(`${private_env.TODO_API}${path}`, {
		...init,
		headers: {
			...headers,
			...init.headers
		}
	});
}

export { todoApi as t };
//# sourceMappingURL=todo-api.js-BuAPWzG1.js.map
