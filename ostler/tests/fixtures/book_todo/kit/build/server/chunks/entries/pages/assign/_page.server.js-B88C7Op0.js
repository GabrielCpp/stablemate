import { t as todoApi } from '../../../chunks/todo-api.js-BuAPWzG1.js';

// src/routes/assign/+page.server.js
async function load({ fetch }) {
	return { todos: await (await todoApi("/todos")(fetch)).json() };
}

var _page_server = /*#__PURE__*/Object.freeze({
	__proto__: null,
	load: load
});

export { _page_server as _ };
//# sourceMappingURL=_page.server.js-B88C7Op0.js.map
