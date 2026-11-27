"""The scripts the browser runs inside a page to read what it shows."""

FIELDS = """root => {
    const KINDS = ['textbox', 'spinbutton', 'combobox', 'checkbox', 'radiogroup', 'switch', 'slider', 'listbox'];
    const shown = (el) => el.checkVisibility ? el.checkVisibility() : !!el.offsetParent;
    const text = (el) => (el.textContent || '').replace(/\\s+/g, ' ').trim();
    const named = (el) => {
        const by = el.getAttribute('aria-labelledby');
        if (by) return by.split(/\\s+/).map((id) => document.getElementById(id)).filter(Boolean).map(text).join(' ');
        if (el.getAttribute('aria-label')) return el.getAttribute('aria-label').trim();
        const set = el.closest('fieldset');
        const legend = set && set.querySelector('legend');
        if (el.getAttribute('role') === 'radiogroup' || el.type === 'radio') return legend ? text(legend) : '';
        if (el.labels && el.labels.length) return [...el.labels].map(text).join(' ');
        return (el.getAttribute('title') || el.getAttribute('placeholder') || '').trim();
    };
    const roleOf = (el) => {
        const given = (el.getAttribute('role') || '').split(/\\s+/)[0];
        if (given) return KINDS.includes(given) ? given : null;
        const tag = el.tagName;
        if (tag === 'TEXTAREA') return 'textbox';
        if (tag === 'SELECT') return el.multiple || el.size > 1 ? 'listbox' : 'combobox';
        if (tag !== 'INPUT') return null;
        const type = (el.getAttribute('type') || 'text').toLowerCase();
        if (type === 'number') return 'spinbutton';
        if (type === 'checkbox') return 'checkbox';
        if (type === 'range') return 'slider';
        if (type === 'radio') return el.closest('[role=radiogroup]') ? null : 'radiogroup';
        return ['hidden', 'button', 'submit', 'reset', 'image', 'file', 'color'].includes(type) ? null : 'textbox';
    };
    const out = [], taken = [], groups = new Set();
    for (const el of root.querySelectorAll('*')) {
        if (!shown(el) || taken.some((outer) => outer.contains(el))) continue;
        const role = roleOf(el);
        if (role === null) continue;
        if (el.type === 'radio') {
            if (groups.has(el.name)) continue;
            groups.add(el.name);
        } else {
            taken.push(el);
        }
        out.push([named(el), role]);
    }
    return out;
}"""
