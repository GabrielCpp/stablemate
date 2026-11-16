import { ai as attr, aj as ensure_array_like, ah as escape_html, a1 as derived } from '../../chunks/server.js-BLCFpuIW.js';
import { p as public_env } from '../../chunks/shared-server.js-B16pR-90.js';
import '../../chunks/client.js-DF54W7-U.js';
import '../../chunks/shared.js-aI2M8oVL.js';
import '../../chunks/index-server.js-XzP0Bcns.js';
import '../../chunks/exports.js-CVS0uUYC.js';
import '../../chunks/internal2.js-DLO42cJ6.js';
import '../../chunks/utils.js-LtVxGe4m.js';

// src/routes/+page.svelte
function _page($$renderer, $$props) {
	$$renderer.component(($$renderer) => {
		let { data, form } = $$props;
		let ready = false;
		const names = derived(() => {
			const given = data.users.map((user) => user.name);
			return public_env.PUBLIC_KIT_BUG === "handed-order" ? given : [...given].sort();
		});
		$$renderer.push(`<h1>Todos</h1> <form method="POST" action="?/add" data-testid="add-form"${attr("data-ready", ready)}><label>Title <input name="title" data-testid="title"/></label> <label>Owner <select name="owner" data-testid="owner">`);
		$$renderer.option({ value: "" }, ($$renderer) => {
			$$renderer.push(`Nobody`);
		});
		$$renderer.push(`<!--[-->`);
		const each_array = ensure_array_like(names());
		for (let $$index = 0, $$length = each_array.length; $$index < $$length; $$index++) {
			let name = each_array[$$index];
			$$renderer.option({ value: name }, ($$renderer) => {
				$$renderer.push(`${escape_html(name)}`);
			});
		}
		$$renderer.push(`<!--]--></select></label> <button data-testid="add">Add</button> `);
		if (form?.error) $$renderer.push(`<!--[0--><p data-testid="error">${escape_html(form.error)}</p>`);
		else $$renderer.push("<!--[-1-->");
		$$renderer.push(`<!--]--></form> <a href="/assign" data-testid="to-assign">Assign</a>`);
	});
}

export { _page as default };
//# sourceMappingURL=_page.svelte.js-Cltdo_yD.js.map
