(() => {
  const EVENTS = ["focus", "blur", "keydown", "beforeinput", "input", "change"];
  const counts = {};
  const attached = new WeakSet();
  let lastInputTrusted = null;
  let submitted = null;
  let extra = () => ({});

  const fieldKey = (el) => el.id || el.name || el.tagName.toLowerCase();

  function onFieldEvent(event) {
    const el = event.composedPath()[0];
    if (el.tagName !== "INPUT") return;
    const bucket = (counts[fieldKey(el)] ??= {});
    bucket[event.type] = (bucket[event.type] || 0) + 1;
    if (event.type === "input") lastInputTrusted = event.isTrusted;
  }

  function onSubmit(event) {
    event.preventDefault();
    submitted = {};
    for (const [name, value] of new FormData(event.target)) {
      submitted[name] = String(value).length;
    }
  }

  function attach(root) {
    if (attached.has(root)) return;
    attached.add(root);
    for (const type of EVENTS) root.addEventListener(type, onFieldEvent, true);
    root.addEventListener("submit", onSubmit);
  }

  function collectInputs(root, into) {
    for (const el of root.querySelectorAll("*")) {
      if (el.tagName === "INPUT" && el.type !== "hidden" && el.type !== "submit") into.push(el);
      if (el.shadowRoot) collectInputs(el.shadowRoot, into);
      if (el.tagName === "IFRAME" && el.contentDocument) collectInputs(el.contentDocument, into);
    }
    return into;
  }

  function deepActive() {
    let active = document.activeElement;
    while (active?.shadowRoot?.activeElement) active = active.shadowRoot.activeElement;
    return active ? fieldKey(active) : null;
  }

  function report() {
    return {
      page: location.pathname,
      documentHasFocus: document.hasFocus(),
      visibility: document.visibilityState,
      active: deepActive(),
      fields: collectInputs(document, []).map((el) => ({
        key: fieldKey(el),
        type: el.type,
        length: el.value.length,
        visible: el.getClientRects().length > 0,
        readOnly: el.readOnly,
      })),
      events: counts,
      lastInputTrusted,
      submitted,
      ...extra(),
    };
  }

  function render() {
    const panel = document.getElementById("probe");
    if (panel) panel.textContent = JSON.stringify(report(), null, 1);
  }

  attach(document);
  window.probe = {
    attach,
    report,
    setExtra: (fn) => { extra = fn; },
  };
  setInterval(render, 250);
})();
