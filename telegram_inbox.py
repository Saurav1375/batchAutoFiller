"""Append job links posted in your Telegram group to links.txt, then delete those messages from the group.

  python3 telegram_inbox.py           # fetch new links (also runs at the start of autofill.py)
  python3 telegram_inbox.py --whoami  # setup: print the chat id of recent messages the bot saw

Whatever is still in the group has not been fetched yet. Telegram keeps unread bot messages for 24 hours,
so links posted while the laptop is off longer are lost.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
LINKS = HERE / "links.txt"
URL = re.compile(r"https?://\S+")


def _env(name):
    val = os.environ.get(name)
    env = HERE / ".env"
    if not val and env.exists():
        for line in env.read_text().splitlines():
            if line.startswith(name + "="):
                val = line.split("=", 1)[1].strip().strip("\"'")
    return val


def _api(token, method, **params):
    url = f"https://api.telegram.org/bot{token}/{method}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)["result"]


def extract(updates, chat_id):
    """{message_id: [urls]} for messages with links in your chat only; anyone else who finds the bot is ignored."""
    found = {}
    for u in updates:
        m = u.get("message") or u.get("edited_message") or {}
        if str(m.get("chat", {}).get("id")) != str(chat_id):
            continue
        urls = [e["url"] for e in m.get("entities", []) + m.get("caption_entities", []) if e["type"] == "text_link"]
        urls += [x.rstrip(".,;:!?)]>'\"") for x in URL.findall(m.get("text") or m.get("caption") or "")]
        if urls:
            found[m["message_id"]] = urls
    return found


def sync():
    """Append new links to links.txt and return them. Does nothing until the bot is set up in .env."""
    token, chat_id = _env("TELEGRAM_BOT_TOKEN"), _env("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return []
    added, offset = [], None
    while True:
        # asking with offset = last id + 1 tells Telegram the earlier ones are done, so they come only once;
        # that happens after links.txt is written, so a crash leaves them on Telegram for the next run
        updates = _api(token, "getUpdates", timeout=0, **({"offset": offset} if offset else {}))
        if not updates:
            return added
        # ponytail: no lock, the timer and autofill.py fetching in the same instant could append a link twice
        text = LINKS.read_text() if LINKS.exists() else ""
        have = {l.strip() for l in text.splitlines()}
        found = extract(updates, chat_id)
        new = [u for u in dict.fromkeys(u for urls in found.values() for u in urls) if u not in have]
        if new:
            LINKS.write_text(text + ("\n" if text and not text.endswith("\n") else "") + "\n".join(new) + "\n")
            added += new
        for message_id in found:  # saved (or already there): clear it from the group
            try:
                _api(token, "deleteMessage", chat_id=chat_id, message_id=message_id)
            except urllib.error.HTTPError:
                pass  # bot not admin, or message older than 48h: it just stays in the group
        offset = updates[-1]["update_id"] + 1


def main():
    if "--whoami" in sys.argv:
        token = _env("TELEGRAM_BOT_TOKEN") or sys.exit("TELEGRAM_BOT_TOKEN missing: add it to .env")
        for u in _api(token, "getUpdates", timeout=0):
            m = u.get("message") or {}
            chat = m.get("chat", {})
            print(chat.get("id"), chat.get("username") or chat.get("first_name"), (m.get("text") or "")[:40])
        return
    for u in sync():
        print("telegram:", u)


if __name__ == "__main__":
    main()
