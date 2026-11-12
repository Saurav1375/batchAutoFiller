// Injected by popup.js into every frame of the tab, after page.js.
// read() returns the fields page.js finds; fill() puts the values autofill.py chose into them.
// Mirrors fill() and fill_combobox() in autofill.py, with page events instead of Playwright's keystrokes.
(globalThis.__afFill = (() => {
  const OPTION = '[role=option], [id*="-option-"], [class*=suggestion], .dropdown-location';
  const norm = s => String(s).toLowerCase().replace(/[^a-z0-9+]+/g, ' ').trim();
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const truthy = v => v === true || ['true', 'yes', 'y', '1', 'checked'].includes(String(v).trim().toLowerCase());
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const shown = el => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden';

  // Index of the best option for value, same rules as pick() in autofill.py: exact, whole-word prefix, all words contained.
  function pick(options, value) {
    const v = norm(value), names = options.map(norm);
    if (!v) return -1;
    if (names.includes(v)) return names.indexOf(v);
    const i = names.findIndex(n => n && ((n + ' ').startsWith(v + ' ') || (v + ' ').startsWith(n + ' ')));
    if (i >= 0) return i;
    return names.findIndex(n => { const words = new Set(n.split(' ')); return v.split(' ').every(w => words.has(w)); });
  }

  // querySelectorAll that also looks inside open shadow roots.
  function all(sel, root = document, out = []) {
    out.push(...root.querySelectorAll(sel));
    for (const el of root.querySelectorAll('*')) if (el.shadowRoot) all(sel, el.shadowRoot, out);
    return out;
  }
  const find = id => all(`[data-af="${id}"]`)[0];
  const visibleOptions = () => all(OPTION).filter(shown);

  function press(el) {  // what a real click sends: some dropdowns open on mousedown, not click
    for (const t of ['pointerdown', 'mousedown', 'pointerup', 'mouseup'])
      el.dispatchEvent(new (t.startsWith('pointer') ? PointerEvent : MouseEvent)(t, { bubbles: true, cancelable: true, view: window }));
    el.click();
  }
  const escape = el => el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));

  function type(el, value) {
    el.focus();
    const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, value);  // native setter: React and co. notice the change
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }

  async function waitOptions() {  // search-as-you-type lists load async
    for (let i = 0; i < 30 && !visibleOptions().length; i++) await sleep(100);
    await sleep(300);  // let a typed search settle before reading
    return visibleOptions();
  }

  async function combo(el, f, value) {
    const place = /\blocation\b|\bcity\b|located/.test(norm(f.question));
    press(el);
    if (f.typeable) type(el, place ? value.split(',')[0] : value.slice(0, 40));  // place search finds "Barh", not "Barh, Bihar, India"
    const opts = await waitOptions();
    let i = pick(opts.map(o => clean(o.innerText)), value);
    if (i < 0 && opts.length && place) i = 0;  // place search takes the top suggestion: check location fields before submitting
    if (i < 0) { escape(el); throw new Error(`no option like "${value}"`); }
    press(opts[i]);
  }

  async function fillOne(f, value, resume) {
    const el = find(f.id) || find(`${f.id}.0`), kind = f.kind;  // radio/checkbox groups tag each option instead
    if (!el) throw new Error('field is gone (page changed?)');
    if (kind === 'text' && /\blocation\b|\bcity\b/.test(norm(f.question))) {
      try { return await combo(el, { ...f, typeable: true }, String(value)); } catch { /* no suggestion list: plain text is fine */ }
    }
    if (kind === 'text' || kind === 'date') {
      type(el, String(value));
      el.blur();
      if (!el.value) throw new Error('value did not stick');
    } else if (kind === 'editable') {
      el.focus();
      document.execCommand('insertText', false, String(value));
    } else if (kind === 'select') {
      const i = pick(f.options, value);
      const opt = i >= 0 && [...el.options].find(o => clean(o.text) === f.options[i]);
      if (!opt) throw new Error(`no option like "${value}"`);
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(el, opt.value);
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    } else if (kind === 'radio' || kind === 'checkbox_group') {
      for (const v of [].concat(value)) {
        const i = pick(f.options, v);
        if (i < 0) throw new Error(`no option like "${v}"`);
        find(`${f.id}.${i}`).click();
      }
    } else if (kind === 'checkbox') {
      const on = el.checked ?? (el.getAttribute('aria-checked') || el.getAttribute('aria-pressed')) === 'true';
      if (truthy(value) !== on) el.click();
    } else if (kind === 'combobox') {
      let error;
      for (const v of [].concat(value)) {
        try { return await combo(el, f, String(v)); } catch (e) { error = e; }
      }
      throw error;
    } else if (kind === 'file') {
      if (!resume) throw new Error('no resume to upload');
      const bytes = Uint8Array.from(atob(resume.data), c => c.charCodeAt(0));
      const dt = new DataTransfer();
      dt.items.add(new File([bytes], resume.name, { type: 'application/pdf' }));
      el.files = dt.files;
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }

  // Fields in this frame. Empty custom dropdowns are opened once to read their options, like peek_options().
  async function read() {
    const r = __af.extract(Math.random().toString(36).slice(2, 7));  // random prefix: ids stay unique across frames
    for (const f of r.fields) {
      if (f.kind !== 'combobox' || f.options.length || f.value) continue;
      const el = find(f.id);
      press(el);
      await sleep(400);
      f.options = visibleOptions().map(o => clean(o.innerText)).filter(Boolean).slice(0, 200);
      escape(el);
    }
    return { ...r, top: window === top, title: document.title, text: window === top ? document.body.innerText.slice(0, 6000) : '' };
  }

  async function fill(items, resume) {
    let filled = 0;
    const problems = [];
    for (const [f, value] of items) {
      try {
        await fillOne(f, value, resume);
        filled++;
      } catch (e) {
        problems.push(`'${f.question.slice(0, 70)}': ${e.message}`);
      }
    }
    return { filled, problems };
  }

  return { read, fill };
})());
