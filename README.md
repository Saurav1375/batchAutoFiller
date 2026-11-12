# batchAutoFiller

Fill job applications on any site from a list of links. It drives your own Chrome, fills every field it can from a dictionary of your details, uses a free AI model only for written answers ("Why do you want to join?"), and **never submits**: you review each form and click Submit yourself.

Tested on Greenhouse, Lever, Ashby, company career pages (e.g. Stripe) and the first steps of Workday.

## How it works

1. Opens each link in a dedicated Chrome profile (your logins persist there), clicking **Apply** / **Apply Manually** if needed.
2. Reads every field on the page: text boxes, dropdowns (native and custom), radio buttons, Yes/No toggles, checkboxes, file uploads, including inside iframes and shadow DOM.
3. Answers each field, in this order:
   - **`dictionary.json`**: regex rules matched against the question, e.g. `"e ?mail"` → your email. A list answer means "acceptable alternatives", so `["Bachelor's Degree", "B.Tech"]` fits whichever option the form offers.
   - **Skill questions** like "Do you have experience with Docker?" → Yes if the skill is in your resume, else No.
   - **AI (OpenRouter free models)** only for free-text questions. It gets your resume text (with email, phone and profile links removed), the job description and the questions. Your dictionary is never sent.
   - **You**: anything still unknown is asked once in the terminal and saved to `dictionary.json` for next time.
4. Clicks **Next / Continue** through multi-step forms and stops before the final submit.
5. Logs every link in `applications.csv`; submitted or skipped links are not opened again.

## Setup

Requires Python 3.10+, Google Chrome and `pdftotext` (`sudo apt install poppler-utils`).

```bash
pip install playwright
python3 -m playwright install chromium     # only needed for test_autofill.py
cp .env.example .env                        # add your free key from https://openrouter.ai
cp config.example.json config.json          # set "resume" to your resume file name
cp dictionary.example.json dictionary.json  # replace placeholders with your details
```

Put your resume PDF in this folder. In `dictionary.json`, entries with `"a": null` are asked in the terminal the first time they come up; fill them now to skip that.

## Usage

```bash
python3 autofill.py                 # every link in links.txt (one URL per line)
python3 autofill.py URL [URL ...]   # just these links
python3 autofill.py --serve         # fill tabs you open yourself, from the Chrome extension
python3 autofill.py --list-free     # free OpenRouter models available right now
python3 test_autofill.py            # self-check on a local two-step form
python3 test_telegram_inbox.py      # self-check for the Telegram fetch
```

### Fill tabs you open yourself (Chrome extension)

Fills the application in whatever tab you are on, in your everyday Chrome, right where it is.

1. Run `python3 autofill.py --serve` and leave the terminal open. It holds your dictionary, resume and AI key; the extension does the reading and typing.
2. Once: `chrome://extensions`, turn on **Developer mode**, **Load unpacked**, pick the `extension/` folder. Chrome warns it can "read and change your data on all websites": it needs that to reach forms inside embedded iframes, and it only acts when you press it.
3. On any application page, click the extension's toolbar button or press **Alt+Shift+F** (change it at `chrome://extensions/shortcuts`).

Each press:
- fills everything `dictionary.json`, your resume and the skill rules can answer, straight away. Nothing is sent to the AI;
- lists the written questions the AI could answer, with a **Write with AI** button. The AI is called only when you click it, and only with those questions. If you close the popup while it writes, press again to fill its answers;
- lists the questions only you can answer. Fill them on the page and press again before clicking Next: your answers are saved to `dictionary.json`.

It fills only the page you're on: click Next yourself and press again on each step. It never submits. After editing anything in `extension/`, press reload on it in `chrome://extensions`.

**Firefox** (128 or newer), instead of step 2:

1. Open `about:debugging#/runtime/this-firefox`, click **Load Temporary Add-on…** and pick `extension/manifest.json`. Firefox removes temporary add-ons when it quits, so repeat this after each restart (or see below).
2. The first press shows **Allow access**: Firefox doesn't grant site access at install. Allow it once (or toggle it in `about:addons` → Application Autofill → Permissions).
3. Change the shortcut at `about:addons` → gear icon → **Manage Extension Shortcuts**.

To keep it installed across restarts, sign it for yourself (free, private, not listed on the store): create API keys at https://addons.mozilla.org/developers/addon/api/key/, then run `npx web-ext sign --source-dir extension --channel unlisted --api-key ... --api-secret ...` and open the `.xpi` it writes in Firefox.

### Send links from your phone (Telegram)

Post job links in a private Telegram group; they land in `links.txt` and are deleted from the group, so whatever is still there has not been fetched yet.

1. In Telegram, open **@BotFather**, send `/newbot`, pick a name. It replies with the token: put it in `.env` as `TELEGRAM_BOT_TOKEN=`.
2. Still in BotFather: `/setprivacy`, choose your bot, **Disable** (so the bot sees plain messages in groups).
3. Create a group, add the bot, and make it **admin** with "Delete messages". Post any message in the group.
4. `python3 telegram_inbox.py --whoami` prints the group's id (a negative number like `-100…`): put it in `.env` as `TELEGRAM_CHAT_ID=`.

Links are fetched at the start of every `python3 autofill.py`. To also fetch every 10 minutes and right after the laptop boots or wakes:

```bash
cp systemd/telegram-inbox.* ~/.config/systemd/user/   # edit the path in the .service if the repo lives elsewhere
systemctl --user daemon-reload && systemctl --user enable --now telegram-inbox.timer
journalctl --user -u telegram-inbox                    # what it fetched
```

Telegram keeps unfetched bot messages for 24 hours, so links posted while the laptop is off longer than that are lost. Messages from any other chat are ignored.

For each link, the terminal shows what was filled and anything left empty. Then:

| Key | Meaning |
|---|---|
| Enter | you submitted it: removed from `links.txt` |
| `r` | fill again (e.g. you moved to the next page yourself) |
| `a` | needs attention, keep for later |
| `s` | skip: stays in `links.txt` as a `# ` comment |

If a page needs login, account creation or a CAPTCHA, it pauses until you finish and press Enter.

## Files

| File | Purpose |
|---|---|
| `autofill.py` | main script: browser, matching, filling, tracking |
| `extension/` | Chrome extension: reads and fills the tab you're on, asks `--serve` for the answers |
| `extension/page.js` | field extractor that runs inside the page (both modes) |
| `ai.py` | OpenRouter client; tries the models in `config.json` in order |
| `system_prompt.md` | instructions for the AI's written answers; edit to change tone |
| `dictionary.example.json` | template for your answers |
| `links.txt` | job links to process |
| `telegram_inbox.py` | pulls links posted in your Telegram group into `links.txt` |

`dictionary.json`, `config.json`, `.env`, your resume and `applications.csv` are git-ignored.

## Notes

- Free models come and go and get rate-limited; keep 3–4 from different providers in `config.json`. `--list-free` shows current ones.
- Location boxes take the site's top suggestion for your city; check them before submitting.
- Bot-check questions ("prove you're not a bot") are left for you on purpose.
- Automating LinkedIn Easy Apply breaks LinkedIn's terms; use company and job-board application pages.
