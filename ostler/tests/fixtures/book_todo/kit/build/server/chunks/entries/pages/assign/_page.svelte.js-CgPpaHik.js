import { ah as escape_html, aj as ensure_array_like, a1 as derived } from '../../../chunks/server.js-BLCFpuIW.js';
import { p as public_env } from '../../../chunks/shared-server.js-B16pR-90.js';
import '../../../chunks/shared.js-aI2M8oVL.js';

// src/routes/assign/+page.svelte
function _page($$renderer, $$props) {
	$$renderer.component(($$renderer) => {
		let { data } = $$props;
		let users = [];
		const names = derived(() => {
			const given = users.map((user) => user.name);
			return public_env.PUBLIC_KIT_BUG === "fetched-order" ? given : [...given].sort();
		});
		$$renderer.push(`<h1>Assign</h1> <p>${escape_html(data.todos.length)} todos</p> <label>Assignee <select data-testid="assignee">`);
		$$renderer.option({ value: "" }, ($$renderer) => {
			$$renderer.push(`Anyone`);
		});
		$$renderer.push(`<!--[-->`);
		const each_array = ensure_array_like(names());
		for (let $$index = 0, $$length = each_array.length; $$index < $$length; $$index++) {
			let name = each_array[$$index];
			$$renderer.option({ value: name }, ($$renderer) => {
				$$renderer.push(`${escape_html(name)}`);
			});
		}
		$$renderer.push(`<!--]--></select></label> <a href="/" data-testid="to-home">Back</a>`);
	});
}

export { _page as default };
//# sourceMappingURL=_page.svelte.js-CgPpaHik.js.map
