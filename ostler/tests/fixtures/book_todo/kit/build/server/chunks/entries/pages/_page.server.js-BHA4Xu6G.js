import { t as todoApi } from '../../chunks/todo-api.js-BuAPWzG1.js';
import { y as fail } from '../../chunks/utils.js-LtVxGe4m.js';

// src/routes/+page.server.js
async function load({ fetch }) {
	return { users: await (await todoApi("/users")(fetch)).json() };
}
var actions = { add: async ({ request, fetch }) => {
	const form = await request.formData();
	const body = { title: String(form.get("title") ?? "") };
	const owner = String(form.get("owner") ?? "");
	if (owner) body.assignee = owner;
	const answer = await todoApi("/todos", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(body)
	})(fetch);
	if (!answer.ok) return fail(answer.status, { error: (await answer.json()).error });
	return { added: true };
} };

var _page_server = /*#__PURE__*/Object.freeze({
	__proto__: null,
	actions: actions,
	load: load
});

export { _page_server as _ };
//# sourceMappingURL=_page.server.js-BHA4Xu6G.js.map
