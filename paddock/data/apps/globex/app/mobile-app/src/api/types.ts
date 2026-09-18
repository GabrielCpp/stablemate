// Matches api-service's JSON shape as store.go defines it (see app/api-service/store.go) —
// nothing here is a guess, it is that struct's field names carried over.
export type Widget = {
  id: string;
  name: string;
  quantity: number;
};

// api-service's 422 body is `{errors: {field: message}}`; the only two fields it ever
// names are the ones Store.Create validates.
export type FieldErrors = {
  name?: string;
  quantity?: string;
};

// What a create attempt hands back: either the widget api-service made, or the field
// errors from its 422 — never both, which is why this is a union rather than two optional
// properties on one object.
export type CreateWidgetResult =
  | { ok: true; widget: Widget }
  | { ok: false; errors: FieldErrors };
