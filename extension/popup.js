// Opening the popup fills the form in this tab, right here: the extension reads the fields, autofill.py
// (`python3 autofill.py --serve`) picks the answers from your dictionary, and the extension types them in.
// The AI is called only when you click "Write with AI".
const SERVER = 'http://127.0.0.1:8765/';
const status = document.getElementById('status');
const out = document.getElementById('out');

// Questions come from arbitrary web pages: always textContent, never innerHTML.
const el = (tag, text = '', cls = '') => Object.assign(document.createElement(tag), { textContent: text, className: cls });

function section(title, items, cls = '') {
  if (!items?.length) return;
  const ul = el('ul', '', cls);
  for (const t of items) ul.append(el('li', t.trim() || '(no label)'));
  out.append(el('h2', title), ul);
}

function say(text, cls = '') {
  status.textContent = text;
  status.className = cls;
}

async function post(body) {
  try {
    const res = await fetch(SERVER, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    return await res.json();
  } catch {
    say('Autofill is not running.', 'warn');
    out.replaceChildren(el('div', 'In the project folder run: python3 autofill.py --serve', 'hint'));
  }
}

// Every frame's fields (forms are often in an iframe), each tagged with the frame it lives in.
async function read(tabId) {
  await chrome.scripting.executeScript({ target: { tabId, allFrames: true }, files: ['page.js', 'fill.js'] });
  const frames = await chrome.scripting.executeScript({ target: { tabId, allFrames: true }, func: () => __afFill.read() });
  const page = { fields: [], login: false, title: '', text: '' };
  for (const { frameId, result } of frames) {
    if (!result) continue;
    page.fields.push(...result.fields.map(f => ({ ...f, frameId })));
    page.login ||= result.password;
    if (result.top) Object.assign(page, { title: result.title, text: result.text });
  }
  return page;
}

async function fill(tabId, fields, plan, resume) {
  const byFrame = new Map();
  for (const f of fields) {
    if (!(f.id in plan)) continue;
    if (!byFrame.has(f.frameId)) byFrame.set(f.frameId, []);
    byFrame.get(f.frameId).push([f, plan[f.id]]);
  }
  const total = { filled: 0, problems: [] };
  for (const [frameId, items] of byFrame) {
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId, frameIds: [frameId] }, func: (items, resume) => __afFill.fill(items, resume), args: [items, resume ?? null],
    });
    total.filled += result.filled;
    total.problems.push(...result.problems);
  }
  return total;
}

async function run(ai) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  say(ai ? 'AI is writing… if you close this, press again later to fill its answers.' : 'Filling from your dictionary…');
  out.replaceChildren();
  let page;
  try {
    page = await read(tab.id);
  } catch (e) {
    return say(`Can't read this page: ${e.message}`, 'warn');
  }
  const r = await post({ url: tab.url, title: page.title, text: page.text, fields: page.fields, ai });
  if (!r) return;
  if (r.error) return say(r.error, 'warn');
  const done = await fill(tab.id, page.fields, r.plan, r.resume);

  if (ai) {
    say(`AI filled ${done.filled} answer${done.filled === 1 ? '' : 's'}.`, r.writing.length || done.problems.length ? 'warn' : 'ok');
    section('Could not fill', done.problems, 'warn');
    section('AI left these empty (see terminal)', r.writing);
    return;
  }
  if (page.login && !r.total) say('Log in first, then press again.', 'warn');
  else if (!r.total) say('No form fields here. Open the application form, then press again.', 'warn');
  else if (!done.filled && !done.problems.length) say('Nothing new to fill on this page.', 'ok');
  else say(`Filled ${done.filled} of ${r.total} fields.`, done.problems.length ? 'warn' : 'ok');
  section('Saved to your dictionary', r.learned);
  section('Could not fill', done.problems, 'warn');
  section('Only you can answer (* = required)', r.asking);
  if (r.asking.length) out.append(el('div', 'Fill them on the page, then press again before Next: your answers are saved for next time.', 'hint'));
  if (r.writing.length) {
    section(`AI can write ${r.writing.length}`, r.writing);
    const b = el('button', 'Write with AI');
    b.onclick = () => run(true);
    out.append(b);
    b.focus();
  }
}

run(false);
