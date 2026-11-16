const manifest = (() => {
function __memo(fn) {
	let value;
	return () => value ??= (value = fn());
}

return {
	appDir: "_app",
	appPath: "_app",
	assets: new Set([]),
	mimeTypes: {},
	_: {
		client: {start:"_app/immutable/entry/start.CvR_mwq8.js",app:"_app/immutable/entry/app.BT8Yo5n5.js",imports:["_app/immutable/entry/start.CvR_mwq8.js","_app/immutable/chunks/CZvpIon1.js","_app/immutable/chunks/aN51gztx.js","_app/immutable/entry/app.BT8Yo5n5.js","_app/immutable/chunks/aN51gztx.js","_app/immutable/chunks/xihTtKlq.js"],stylesheets:[],fonts:[],uses_env_dynamic_public:true},
		nodes: [
			__memo(() => import('./nodes/0.js-__vqUDWz.js')),
			__memo(() => import('./nodes/1.js-E2ryz8zp.js')),
			__memo(() => import('./nodes/2.js-vlXOKOwE.js')),
			__memo(() => import('./nodes/3.js-CP8w9wym.js'))
		],
		remotes: {
			
		},
		routes: [
			{
				id: "/",
				pattern: /^\/$/,
				params: [],
				page: { layouts: [0,], errors: [1,], leaf: 2 },
				endpoint: null
			},
			{
				id: "/api/todos",
				pattern: /^\/api\/todos\/?$/,
				params: [],
				page: null,
				endpoint: __memo(() => import('./entries/endpoints/api/todos/_server.js-CuAak_4g.js'))
			},
			{
				id: "/api/users",
				pattern: /^\/api\/users\/?$/,
				params: [],
				page: null,
				endpoint: __memo(() => import('./entries/endpoints/api/users/_server.js-V8ZaeePj.js'))
			},
			{
				id: "/assign",
				pattern: /^\/assign\/?$/,
				params: [],
				page: { layouts: [0,], errors: [1,], leaf: 3 },
				endpoint: null
			}
		],
		prerendered_routes: new Set([]),
		matchers: async () => {
			
			return {  };
		},
		server_assets: {}
	}
}
})();

export { manifest as m };
//# sourceMappingURL=manifest.js-B3ZEuaMq.js.map
