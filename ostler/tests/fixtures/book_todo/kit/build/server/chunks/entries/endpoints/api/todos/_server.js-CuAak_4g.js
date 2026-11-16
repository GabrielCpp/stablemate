import { t as todoApi } from '../../../../chunks/todo-api.js-BuAPWzG1.js';
import { j as json } from '../../../../chunks/utils.js-LtVxGe4m.js';
import '../../../../chunks/shared-server.js-B16pR-90.js';
import '../../../../chunks/shared.js-aI2M8oVL.js';

// src/routes/api/todos/+server.js
async function GET({ fetch }) {
	const answer = await todoApi("/todos")(fetch);
	return json(await answer.json());
}

export { GET };
//# sourceMappingURL=_server.js-CuAak_4g.js.map
