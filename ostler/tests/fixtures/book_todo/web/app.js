const EN = {
  title: "Todos", search: "Search", assignee: "Assignee", status: "Status", anyone: "Anyone", any: "Any",
  unscheduled: "Unscheduled", scheduled: "Scheduled", overdue: "Overdue", loading: "Loading",
  empty: "Nothing to do", edit: "Edit", remove: "Remove", offline: "You're offline", addForm: "Add a todo",
  editForm: "Edit todo", todoTitle: "Title", description: "Description", due: "Due date", nobody: "Nobody",
  save: "Save", saving: "Saving", cancel: "Cancel", clearDue: "Clear due date",
  removeQuestion: "Remove this todo?", removeConfirm: "Yes, remove", removeCancel: "Keep it",
  failed: "Request failed", details: "Details",
};
const FR = {
  title: "Tâches", search: "Rechercher", assignee: "Responsable", status: "État", anyone: "Tous", any: "Tous",
  unscheduled: "Sans date", scheduled: "Planifiée", overdue: "En retard", loading: "Chargement",
  empty: "Rien à faire", edit: "Modifier", remove: "Supprimer", offline: "Vous êtes hors ligne",
  addForm: "Ajouter une tâche", editForm: "Modifier la tâche", todoTitle: "Titre", description: "Description",
  due: "Échéance", nobody: "Personne", save: "Enregistrer", saving: "Enregistrement", cancel: "Annuler",
  clearDue: "Effacer l'échéance", removeQuestion: "Supprimer cette tâche ?", removeConfirm: "Oui, supprimer",
  removeCancel: "Garder", failed: "Échec de la requête", details: "Détails",
};

const query = new URLSearchParams(location.search).get("lang");
const french = query === "fr" || (query !== "en" && navigator.language.toLowerCase().startsWith("fr"));
const t = (key) => (french ? FR : EN)[key];

function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === false) continue;
    if (name.startsWith("on")) el.addEventListener(name.slice(2), value);
    else if (name === "value") el.value = value;
    else el.setAttribute(name, value === true ? "" : value);
  }
  el.append(...children);
  return el;
}

async function call(path, init = {}) {
  let res;
  try {
    res = await fetch(window.API_URL + path, {
      ...init,
      headers: { Authorization: "Bearer test-token", ...(init.body ? { "Content-Type": "application/json" } : {}) },
    });
  } catch {
    throw new Error(t("failed"));
  }
  if (!res.ok) {
    let message = t("failed");
    try {
      message = (await res.json()).error || message;
    } catch {
      message = t("failed");
    }
    throw new Error(message);
  }
  return res;
}

const addForms = [];
const state = { rows: [], loaded: false, online: navigator.onLine, text: "", assignee: "", status: "", editing: null, removing: null };
let sequence = 0;
const root = document.getElementById("root");
const main = h("main");
root.append(main);

let people = [];
const userSelects = [];

function fillUsers(select, first) {
  const kept = select.value;
  const offered = window.BUG === "missing-user" && select.id === "list-assignee" ? people.slice(0, -1) : people;
  select.replaceChildren(h("option", { value: "" }, first), ...offered.map((name) => h("option", { value: name }, name)));
  select.value = kept;
  if (window.BUG === "preselect-user" && !kept && offered.length) select.value = offered[0];
}

function users(select, first) {
  fillUsers(select, first);
  userSelects.push([select, first]);
}

async function loadUsers() {
  try {
    people = (await (await call("/users")).json()).map((user) => user.name);
    if (window.BUG !== "unsorted-users") people.sort();
    if (window.BUG === "duplicate-user" && people.length) people.splice(1, 0, people[0]);
    for (const [select, first] of userSelects) fillUsers(select, first);
  } catch {
    people = [];
  }
}

function fields(prefix, todo, onTouch) {
  const title = h("input", { id: `${prefix}-title`, "data-testid": "todo-title", value: todo.title || "", oninput: onTouch });
  const description = h("textarea", { id: `${prefix}-description`, "data-testid": "todo-description", oninput: onTouch });
  description.value = todo.description || "";
  const due = h("input", { id: `${prefix}-due`, type: "date", "data-testid": "todo-due", value: todo.due_on || "", oninput: onTouch });
  const assignee = h("select", { id: `${prefix}-assignee`, "data-testid": "todo-assignee", onchange: onTouch });
  users(assignee, t("nobody"));
  assignee.value = todo.assignee || "";
  return { title, description, due, assignee };
}

function form(kind, todo, done, cancel) {
  const adding = kind === "add";
  const prefix = adding ? "add" : `edit-${todo.id}`;
  let phase = "idle";
  let cleared = false;
  const error = h("p", { "data-testid": "todo-error", role: "alert" });
  const spinner = h("span", { "data-testid": "todo-saving", role: "progressbar", "aria-label": t("saving") }, "…");
  const save = h("button", { type: "submit", "data-testid": "todo-save" }, t("save"));
  const clear = h("button", { type: "button", "data-testid": "todo-due-clear" }, t("clearDue"));
  const dismiss = h("button", { type: "button", "data-testid": "todo-cancel", onclick: cancel }, t("cancel"));
  const touch = () => {
    if (phase === "refused") phase = "idle";
    refresh();
  };
  const f = fields(prefix, todo, touch);
  const labelled = (id, text, el) => h("div", {}, h("label", { for: id }, text), el);
  function refresh() {
    const saving = phase === "saving";
    for (const el of [f.title, f.description, f.due, f.assignee, clear, dismiss]) el.disabled = saving;
    save.disabled = saving || !state.online || f.title.value.trim() === "";
    if (state.online) save.removeAttribute("title");
    else save.setAttribute("title", t("offline"));
    spinner.hidden = !saving;
    error.hidden = phase !== "refused";
  }
  clear.addEventListener("click", () => {
    f.due.value = "";
    cleared = true;
    touch();
  });
  f.due.addEventListener("input", () => {
    cleared = f.due.value === "";
  });
  const el = h("form", { "data-testid": `${kind}-form`, "aria-label": t(adding ? "addForm" : "editForm") },
    labelled(`${prefix}-title`, t("todoTitle"), f.title),
    labelled(`${prefix}-description`, t("description"), f.description),
    h("div", {}, h("label", { for: `${prefix}-due` }, t("due")), f.due, adding ? "" : clear),
    labelled(`${prefix}-assignee`, t("assignee"), f.assignee),
    save, adding ? "" : dismiss, spinner, error);
  el.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (phase === "saving" || !state.online || f.title.value.trim() === "") return;
    let body;
    if (adding) {
      body = { title: f.title.value };
      if (f.description.value) body.description = f.description.value;
      if (f.due.value) body.due_on = f.due.value;
      if (f.assignee.value) body.assignee = f.assignee.value;
    } else {
      body = {
        title: f.title.value,
        description: f.description.value === "" ? null : f.description.value,
        due_on: cleared || f.due.value === "" ? null : f.due.value,
        assignee: f.assignee.value === "" ? null : f.assignee.value,
      };
      if (window.BUG === "wrong-assignee" && body.assignee === "bo") body.assignee = "ana";
    }
    if (window.BUG === "utc-midnight" && body.due_on) body.due_on = new Date(`${body.due_on}T00:00:00+02:00`).toISOString().slice(0, 10);
    phase = "saving";
    error.textContent = "";
    refresh();
    try {
      await call(adding ? "/todos" : `/todos/${todo.id}`, { method: adding ? "POST" : "PUT", body: JSON.stringify(body) });
      phase = "idle";
      if (adding) {
        f.title.value = "";
        f.description.value = "";
        f.due.value = "";
        f.assignee.value = "";
      }
      refresh();
      done();
    } catch (failure) {
      error.textContent = failure.message;
      phase = "refused";
      refresh();
    }
  });
  if (adding) addForms.push(refresh);
  refresh();
  return el;
}

function dialog(id) {
  let phase = "idle";
  const error = h("p", { role: "alert" });
  const confirm = h("button", { type: "button", "data-testid": "remove-confirm" }, t("removeConfirm"));
  const keep = h("button", { type: "button", "data-testid": "remove-cancel", onclick: () => { state.removing = null; render(); } }, t("removeCancel"));
  const refresh = () => {
    confirm.disabled = phase === "saving" || !state.online;
    if (state.online) confirm.removeAttribute("title");
    else confirm.setAttribute("title", t("offline"));
    error.hidden = phase !== "refused";
  };
  confirm.addEventListener("click", async () => {
    phase = "saving";
    error.textContent = "";
    refresh();
    try {
      await call(`/todos/${id}`, { method: "DELETE" });
      state.removing = null;
      load();
      render();
    } catch (failure) {
      error.textContent = failure.message;
      phase = "refused";
      refresh();
    }
  });
  refresh();
  return h("div", { role: "dialog", "aria-modal": "true", "aria-label": t("removeQuestion"), "data-testid": "remove-dialog" },
    h("p", {}, t("removeQuestion")), error, confirm, keep);
}

function row(todo) {
  if (state.editing === todo.id) {
    return h("li", { "data-testid": "todo-row", "data-id": todo.id },
      form("edit", todo, () => { state.editing = null; load(); render(); }, () => { state.editing = null; render(); }));
  }
  const remove = h("button", { type: "button", "data-testid": "row-remove", onclick: () => { state.removing = todo.id; render(); } }, t("remove"));
  remove.disabled = !state.online;
  if (!state.online) remove.setAttribute("title", t("offline"));
  return h("li", { "data-testid": "todo-row", "data-id": todo.id },
    h("span", { "data-testid": "row-title" }, todo.title),
    h("span", { "data-testid": "row-assignee" }, todo.assignee || ""),
    h("span", { "data-testid": "row-due" }, todo.due_on || ""),
    h("span", { "data-testid": "row-status" }, t(todo.status)),
    h("button", { type: "button", "data-testid": "row-edit", onclick: () => { state.editing = todo.id; render(); } }, t("edit")),
    remove);
}

const list = h("ul", { "data-testid": "todo-list" });
const banner = h("div", { "data-testid": "offline-banner", role: "status" }, t("offline"));
const loading = h("span", { "data-testid": "list-loading", role: "progressbar", "aria-label": t("loading") }, "…");
const empty = h("p", { "data-testid": "list-empty" }, t("empty"));
const dialogs = h("div");
let debounce = 0;

function render() {
  banner.hidden = state.online;
  loading.hidden = state.loaded;
  empty.hidden = !(state.loaded && state.rows.length === 0);
  list.replaceChildren(...state.rows.map(row));
  dialogs.replaceChildren(...(state.removing === null ? [] : [dialog(state.removing)]));
  for (const refresh of addForms) refresh();
}

async function load() {
  if (!state.online) return;
  const mine = ++sequence;
  const p = new URLSearchParams();
  if (state.text) p.set("text", state.text);
  if (state.assignee) p.set("assignee", state.assignee);
  if (state.status) p.set("status", state.status);
  try {
    const rows = await (await call(`/todos?${p.toString()}`)).json();
    if (mine === sequence) {
      state.rows = window.BUG === "drop-last" ? rows.slice(0, -1) : rows;
      state.loaded = true;
      render();
    }
  } catch {
    if (mine === sequence) {
      state.loaded = true;
      render();
    }
  }
}

const search = h("input", {
  id: "list-search", type: "search", "data-testid": "list-search",
  oninput: () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => { state.text = search.value; load(); }, 150);
  },
});
const assignee = h("select", { id: "list-assignee", "data-testid": "list-assignee", onchange: () => { state.assignee = assignee.value; load(); } });
users(assignee, t("anyone"));
const STATUS_CHOICES = [["", t("any")], ...["unscheduled", "scheduled", "overdue"].map((s) => [s, t(s)])];
const statusList = h("ul", { id: "list-status-options", role: "listbox", "aria-label": t("status"), hidden: true });
const status = h("button", {
  type: "button", id: "list-status", "data-testid": "list-status", role: "combobox",
  "aria-haspopup": "listbox", "aria-expanded": "false", "aria-controls": "list-status-options",
  onclick: () => setStatusOpen(statusList.hidden),
}, t("any"));

function setStatusOpen(open) {
  statusList.hidden = !open;
  status.setAttribute("aria-expanded", open ? "true" : "false");
}

for (const [value, text] of STATUS_CHOICES) {
  statusList.append(h("li", {
    role: "option", "data-value": value,
    onclick: () => {
      status.textContent = text;
      setStatusOpen(false);
      state.status = value;
      load();
    },
  }, text));
}
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") setStatusOpen(false);
});

const details = h("form", { "data-testid": "details-form", "aria-label": t("details") });

function control(index, field) {
  const id = `details-${index}`;
  if (field.type === "choice") return h("select", { id }, ...field.options.map((option) => h("option", { value: option }, option)));
  if (field.type === "flag") return h("input", { id, type: "checkbox" });
  if (field.type === "longtext") return h("textarea", { id });
  const number = field.type === "number" && window.BUG !== "wrong-kind";
  return h("input", { id, type: number ? "number" : "text" });
}

async function loadDetails() {
  try {
    const definition = await (await fetch("/definition")).json();
    definition.fields.forEach((field, index) => {
      details.append(h("div", {}, h("label", { for: `details-${index}` }, field.label), control(index, field)));
    });
  } finally {
    details.dataset.ready = "yes";
  }
}

const adding = form("add", {}, load, () => {});
main.append(
  h("h1", { "data-testid": "list-title" }, t("title")), banner, adding,
  h("div", {}, h("label", { for: "list-search" }, t("search")), search,
    h("label", { for: "list-assignee" }, t("assignee")), assignee,
    h("label", { for: "list-status" }, t("status")), status, statusList),
  details, loading, empty, list, dialogs);

window.addEventListener("online", () => { state.online = true; load(); render(); });
window.addEventListener("offline", () => { state.online = false; render(); });
render();
loadUsers();
loadDetails();
load();
