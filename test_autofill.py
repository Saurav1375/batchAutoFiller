"""Self-check: fills a local two-step form with a stubbed AI. Run: python3 test_autofill.py"""
import tempfile
from types import SimpleNamespace

from playwright.sync_api import sync_playwright

import ai
import autofill

FORM = """<form onsubmit="window.submitted = true; return false">
<div id=s1>
  <label for=fn>First name *</label><input id=fn required>
  <label for=ln>Last name</label><input id=ln name=last_name>
  <input type=email autocomplete=email placeholder="you@example.com">
  <div>Are you legally authorized to work in India?</div>
  <label><input type=radio name=auth value=y style="opacity:0;position:absolute"> Yes</label>
  <label><input type=radio name=auth value=n style="opacity:0;position:absolute"> No</label>
  <label for=exp>Years of experience</label>
  <select id=exp><option value="">Select...</option><option>0-1</option><option>2-4</option><option>5+</option></select>
  <div>Notice period</div>
  <div role=combobox id=np tabindex=0 aria-expanded=false>Select one</div>
  <ul role=listbox id=np-list hidden><li role=option>Immediate</li><li role=option>30 days</li><li role=option>60 days</li></ul>
  <label>Resume <input type=file id=cv style="display:none"></label>
  <label><input type=checkbox id=agree> I agree to the privacy policy</label>
  <div id=host></div>
  <button type=button id=next>Next</button>
</div>
<div id=s2 hidden>
  <label for=why>Why do you want to work here?</label><textarea id=why></textarea>
  <button type=submit>Submit application</button>
</div>
</form>
<script>
  const np = document.getElementById('np'), list = document.getElementById('np-list');
  np.onclick = () => list.hidden = !list.hidden;
  for (const o of list.children) o.onclick = () => { np.textContent = o.textContent; list.hidden = true; };
  document.addEventListener('keydown', e => { if (e.key === 'Escape') list.hidden = true; });
  document.getElementById('host').attachShadow({mode: 'open'}).innerHTML = '<label for=city>City</label><input id=city>';
  document.getElementById('next').onclick = () => { s1.hidden = true; s2.hidden = false; };
</script>"""

DICTIONARY = [
    {"q": "first ?name", "a": "Ashish"}, {"q": "last ?name", "a": "K"}, {"q": "e ?mail", "a": "a@b.c"},
    {"q": "authori[sz]", "a": "Yes"}, {"q": "years of experience", "a": ["0", "0-1"]},
    {"q": "notice", "a": "30 days"}, {"q": "^city", "a": "Pune"}, {"q": "privacy", "a": True},
]


def fake_chat(models, system, user):
    import json
    questions = json.loads(user)["questions"]
    asked.extend(q["question"] for q in questions)
    return {"answers": [{"id": q["id"], "value": "Because."} for q in questions]}, "stub"


asked = []
ai.chat = fake_chat
autofill.DICTIONARY = autofill.Path(tempfile.mkdtemp()) / "dictionary.json"

with tempfile.NamedTemporaryFile(suffix=".pdf") as resume, sync_playwright() as p:
    page = p.chromium.launch().new_context().new_page()
    page.set_content(FORM)
    ctx = SimpleNamespace(dictionary=DICTIONARY, resume="", resume_words=set(), resume_path=autofill.Path(resume.name), job={}, models=["stub"], system="")
    problems = autofill.fill_form(page, ctx)
    v = lambda sel: page.eval_on_selector(sel, "e => e.value")
    assert problems == [], problems
    assert (v("#fn"), v("#ln"), v("input[type=email]")) == ("Ashish", "K", "a@b.c")
    assert page.is_checked("input[value=y]")
    assert page.eval_on_selector("#exp", "e => e.selectedOptions[0].text") == "0-1"
    assert page.inner_text("#np") == "30 days"
    assert page.eval_on_selector("#cv", "e => e.files.length") == 1
    assert page.is_checked("#agree")
    assert page.evaluate("document.getElementById('host').shadowRoot.getElementById('city').value") == "Pune"
    assert v("#why") == "Because."
    assert not page.evaluate("window.submitted"), "must never submit"
    assert asked == ["Why do you want to work here?"], f"only free text goes to AI: {asked}"
    assert autofill.pick(["Yes, I am authorized", "No"], "yes") == "Yes, I am authorized"
    assert autofill.pick(["Not applicable", "No"], "no") == "No"
    assert autofill.pick(["Male", "Female", "I decline to self-identify"], "decline") == "I decline to self-identify"
    words = set(autofill.norm("Python, React.js, Docker, C++").split())
    yn = lambda q: autofill.skill_answer({"question": q, "kind": "radio", "options": ["Yes", "No"]}, words)
    assert yn("Do you have experience with Docker?") == "Yes"
    assert yn("Are you familiar with React.js or Vue?") == "Yes"
    assert yn("Do you have experience building software in AWS (with Terraform)?") == "No"
    assert yn("Do you have 5+ years of experience with Python?") is None
    clean = autofill.redact("+91 9876543210  # me@mail.com  linkedin.com/in/x/ https://github.com/y 1.3M+ ops, 2023 – 2027, 100K+")
    assert not any(x in clean for x in ("9876543210", "@", "linkedin", "github")) and "1.3M+" in clean and "2023 – 2027" in clean, clean
    # learning: what you answer (or skip) in the terminal is saved and reused without asking
    base = dict(kind="text", value="", options=[], name="", placeholder="", autocomplete="")
    color = dict(base, id="a", question="Favourite colour", required=True)
    robots = dict(base, id="b", question="Nickname for robots", required=False)
    learn = SimpleNamespace(dictionary=[], resume_words=set(), resume_path=autofill.Path("/nonexistent"))
    autofill.ask_user = lambda f: {"Favourite colour": "Blue"}.get(f["question"])
    assert autofill.decide([color, robots], learn) == {"a": "Blue"}
    autofill.ask_user = lambda f: (_ for _ in ()).throw(AssertionError(f"asked again: {f['question']}"))
    assert autofill.decide([color, robots], learn) == {"a": "Blue"}
    assert len(autofill.json.loads(autofill.DICTIONARY.read_text())) == 2
    # --serve: dictionary answers right away, AI only when asked, your typed answers learned on the next press
    press = SimpleNamespace(dictionary=DICTIONARY[:1], resume="", resume_words=set(), resume_path=autofill.Path(resume.name), job={}, models=["stub"], system="")
    blank = dict(value="", options=[], name="", placeholder="", autocomplete="", required=False)
    form = [dict(blank, id="x-0", kind="text", question="First name"), dict(blank, id="x-1", kind="text", input_type="textarea", question="Why us?"),
            dict(blank, id="x-2", kind="text", question="Expected CTC", required=True), dict(blank, id="x-3", kind="file", question="Resume")]
    memory, asked[:] = {}, []
    req = lambda **kw: {"url": "https://jobs.test/apply", "fields": form, **kw}
    r = autofill.handle(press, memory, req())
    assert (r["plan"], r["writing"], r["asking"], asked) == ({"x-0": "Ashish", "x-3": resume.name}, ["Why us?"], ["Expected CTC *"], []), r
    assert r["resume"]["name"] == autofill.Path(resume.name).name
    r = autofill.handle(press, memory, req(ai=True, text="Robotics intern at Acme"))
    assert (r["plan"], asked, press.job["description"]) == ({"x-1": "Because."}, ["Why us?"], "Robotics intern at Acme"), r
    form[0]["value"], form[2]["value"], form[3]["value"] = "Ashish", "6 LPA", "set"  # you typed the CTC; popup closed before the AI answer landed
    r = autofill.handle(press, memory, req())
    assert (r["learned"], r["plan"], r["asking"], r["writing"], len(asked)) == (["Expected CTC"], {"x-1": "Because."}, [], [], 1), r
    assert press.dictionary[0]["a"] == "6 LPA"

    # the extension itself fills the form in place, answered by a --serve running in this process
    import shutil, threading, time
    ext = tempfile.mkdtemp()  # a copy talking to a spare port, so a --serve you have running is left alone
    shutil.copytree(autofill.HERE / "extension", ext, dirs_exist_ok=True)
    js = autofill.Path(ext, "popup.js")
    js.write_text(js.read_text().replace(f":{autofill.SERVE_PORT}/", ":8799/"))
    autofill.SERVE_PORT = 8799
    threading.Thread(target=autofill.serve, daemon=True, args=(SimpleNamespace(
        dictionary=list(DICTIONARY), resume="", resume_words=set(), resume_path=autofill.Path(resume.name), job={}, models=["stub"], system=""),)).start()
    chrome = p.chromium.launch_persistent_context(tempfile.mkdtemp(), channel="chromium", headless=True,
                                                  args=[f"--disable-extensions-except={ext}", f"--load-extension={ext}"])
    chrome.route("https://jobs.test/form", lambda r: r.fulfill(content_type="text/html", body=FORM))
    job = chrome.new_page()
    job.goto("https://jobs.test/form")
    page = chrome.new_page()
    page.goto("chrome://extensions")
    ext_id = page.evaluate("chrome.management.getAll().then(a => a[0].id)")
    page.add_init_script("const q = chrome.tabs.query.bind(chrome.tabs); chrome.tabs.query = () => q({url: 'https://jobs.test/*'})")  # stands in for 'the tab you were on'

    def popup_result():
        for _ in range(60):
            if "…" not in page.inner_text("#status"):
                return page.inner_text("body")
            time.sleep(0.25)
        raise AssertionError(page.inner_text("body"))

    asked[:] = []
    page.goto(f"chrome-extension://{ext_id}/popup.html")
    shown = popup_result()
    v = lambda sel: job.eval_on_selector(sel, "e => e.value")
    assert "Filled 9 of 9 fields." in shown, shown
    assert (v("#fn"), v("#ln"), v("input[type=email]")) == ("Ashish", "K", "a@b.c")
    assert job.is_checked("input[value=y]") and job.is_checked("#agree")
    assert job.eval_on_selector("#exp", "e => e.selectedOptions[0].text") == "0-1"
    assert job.inner_text("#np") == "30 days"
    assert job.eval_on_selector("#cv", "e => e.files.length") == 1
    assert job.evaluate("document.getElementById('host').shadowRoot.getElementById('city').value") == "Pune"
    job.click("#next")
    page.reload()
    shown = popup_result()
    assert "ai can write 1" in shown.lower() and asked == [], shown  # headings render uppercase
    page.click("text=Write with AI")
    assert "AI filled 1 answer." in popup_result() and v("#why") == "Because."
    assert not job.evaluate("window.submitted"), "must never submit"
# links.txt: submitted links leave, skipped ones become comments, the rest stay
autofill.LINKS = autofill.Path(tempfile.mkdtemp()) / "links.txt"
autofill.LINKS.write_text("https://a.test\nhttps://b.test\nhttps://c.test")
autofill.mark_done("https://a.test", "submitted")
autofill.mark_done("https://b.test", "skipped")
autofill.mark_done("https://c.test", "needs-attention")
assert autofill.LINKS.read_text() == "# https://b.test\nhttps://c.test", autofill.LINKS.read_text()
print("ok")
